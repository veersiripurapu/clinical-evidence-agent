"""
evidence_extractor.py

Pipeline step: take the evidence cards the retriever pulled and crack each one
open into clean, structured "evidence units" the brief generator can assemble.

For each card it extracts:
- source_id, title, citation label, url  (so every claim can be traced)
- allowed_claims   (what the brief MAY assert from this source)
- not_allowed_claims  (the fences: what the brief must NOT assert)
- the plain summary text

Plain code, no AI: it can only surface what is literally written in the card.
It also self-checks and warns if an expected section is missing, so a mistyped
heading can't silently disappear.
"""

import re
import frontmatter
from pathlib import Path


# The exact headings we expect in every card body
HEADING_ALLOWED = "Claims allowed from this source"
HEADING_NOT_ALLOWED = "Claims NOT allowed from this source"
HEADING_CITATION = "Citation label"
HEADING_SUMMARY = "User-authored summary"


def split_sections(body_text):
    """
    Split a markdown body into {heading_text: section_body} using '## ' headings.
    """
    sections = {}
    current_heading = None
    current_lines = []

    for line in body_text.splitlines():
        heading_match = re.match(r"^##\s+(.*)$", line.strip())
        if heading_match:
            # Save the previous section before starting a new one
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = heading_match.group(1).strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def extract_bullets(section_text):
    """
    Pull bullets from a section, stitching wrapped continuation lines back
    together. A bullet starts with '- ', '* ', or '+ '. Any indented line
    beneath it is treated as a continuation of the same bullet.

    So a claim that wraps across two lines in the card is rejoined into one
    complete sentence — important, because these become the controlled claims
    the brief may use and the citation-verifier checks against.
    """
    bullets = []
    current_parts = []

    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            continue  # skip blank lines

        bullet_match = re.match(r"^\s*[-*+]\s+(.*)", raw_line)

        if bullet_match:
            # A new bullet begins: save the previous one first
            if current_parts:
                bullets.append(" ".join(current_parts).strip())
            current_parts = [bullet_match.group(1).strip()]

        elif current_parts and (raw_line.startswith(" ") or raw_line.startswith("\t")):
            # Indented line under a bullet = continuation of that bullet
            current_parts.append(stripped)

        else:
            # A non-indented, non-bullet line ends the current bullet
            if current_parts:
                bullets.append(" ".join(current_parts).strip())
                current_parts = []

    if current_parts:  # don't forget the last bullet
        bullets.append(" ".join(current_parts).strip())

    return bullets


def extract_from_card(card):
    """Turn one retrieved card into a structured evidence unit, with self-check."""
    body = card.get("summary_text", "")
    sections = split_sections(body)

    warnings = []

    allowed_section = sections.get(HEADING_ALLOWED)
    not_allowed_section = sections.get(HEADING_NOT_ALLOWED)
    citation_section = sections.get(HEADING_CITATION)
    summary_section = sections.get(HEADING_SUMMARY, "")

    if allowed_section is None:
        warnings.append(f"Missing section: '{HEADING_ALLOWED}'")
    if not_allowed_section is None:
        warnings.append(f"Missing section: '{HEADING_NOT_ALLOWED}'")
    if citation_section is None:
        warnings.append(f"Missing section: '{HEADING_CITATION}'")

    allowed_claims = extract_bullets(allowed_section) if allowed_section else []
    not_allowed_claims = extract_bullets(not_allowed_section) if not_allowed_section else []

    return {
        "source_id": card.get("source_id"),
        "title": card.get("title"),
        "citation_label": (citation_section or card.get("source_id") or "").strip(),
        "citation": card.get("source_citation", ""),
        "url": card.get("source_url", ""),
        "summary": summary_section.strip(),
        "allowed_claims": allowed_claims,
        "not_allowed_claims": not_allowed_claims,
        "warnings": warnings,
    }


def extract_all(retrieved_results):
    """
    retrieved_results: the list of dicts from evidence_retriever.retrieve()
    Returns a list of structured evidence units.
    """
    units = []
    for r in retrieved_results:
        card = r["card"]
        unit = extract_from_card(card)
        unit["retrieval_score"] = r.get("score")
        units.append(unit)
    return units


def main():
    # Run the retriever, then extract from what it pulled — the real pipeline flow.
    from evidence_retriever import (
        retrieve, load_patient, build_patient_context
    )

    base = Path("data")
    patient_file = base / "patients" / "synthetic_patient_001.json"
    summaries_dir = base / "evidence" / "summaries"

    question = (
        "For adults with severe knee osteoarthritis and persistent functional "
        "limitation after conservative therapy, what are the benefits, risks, and "
        "evidence limitations of orthopedic evaluation for surgical management "
        "compared with continued or optimized non-surgical management?"
    )

    patient = load_patient(patient_file)
    retrieval_text = question + " " + build_patient_context(patient)
    results, _ = retrieve(retrieval_text, summaries_dir, top_k=6)

    units = extract_all(results)

    print("=" * 60)
    print("EVIDENCE EXTRACTION")
    print("=" * 60)

    any_warnings = False
    for u in units:
        print(f"\n[{u['source_id']}] {u['title']}")
        print(f"  Citation: {u['citation_label']}")
        print(f"  Allowed claims:     {len(u['allowed_claims'])}")
        for c in u["allowed_claims"]:
            print(f"     + {c}")
        print(f"  NOT-allowed claims: {len(u['not_allowed_claims'])}")
        for c in u["not_allowed_claims"]:
            print(f"     - {c}")
        if u["warnings"]:
            any_warnings = True
            print("  ** WARNINGS:")
            for w in u["warnings"]:
                print(f"     !! {w}")

    print("\n" + "=" * 60)
    if any_warnings:
        print("SELF-CHECK: Some cards had missing sections (see WARNINGS above).")
        print("Fix the card headings so every fence is captured.")
    else:
        print("SELF-CHECK: All cards parsed cleanly. Every fence captured.")
    print("=" * 60)


if __name__ == "__main__":
    main()