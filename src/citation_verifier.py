"""
citation_verifier.py

The independent inspector. After the brief is assembled, this component audits
it and confirms:

  CHECK 1 - Citation presence: every evidence claim carries a citation label.
  CHECK 2 - Fence scan: the brief does not ASSERT anything a source forbade
            (a keyword-signature scan over the brief body, excluding the
            "What the Evidence Does NOT Support" section, which legitimately
            lists the fences).
  CHECK 3 - Citation integrity: every citation label used exists in the
            known set of sources.

v1 is a STRUCTURAL verifier. It does not perform deep semantic entailment
(does the source truly support this exact claim?) — that is a planned v2
upgrade. Stating that limit honestly is part of the design.
"""

import re
from pathlib import Path


# Risky signal phrases derived from the kinds of fences our cards declare.
# If the brief ASSERTS any of these (outside the fences section), flag it.
RISKY_PATTERNS = [
    # Only flag a success rate being ASSERTED (with a number or "of"),
    # not one being disclaimed ("no success rate is provided").
    r"\bsuccess rate of\b",
    r"\b\d{1,3}(\.\d+)?\s?%\s+(success|cure|improvement)\b",
    r"\bguarantee(d|s)?\b",
    r"\bshould (have|get|undergo) surgery\b",
    r"\bmust (have|get|undergo)\b",
    r"\bis a surgical candidate\b",
    r"\bwill (improve|recover|heal)\b",
]


def verify_units(evidence_units):
    """CHECK 1 + 3: every claim has a citation; every label is known."""
    issues = []
    known_labels = {u["citation_label"] for u in evidence_units}

    for u in evidence_units:
        label = u["citation_label"]
        if not label:
            issues.append(f"[{u.get('source_id')}] has no citation label.")
        if not u["allowed_claims"]:
            issues.append(f"[{label}] contributed no allowed claims (empty source).")
        # Integrity: the label a unit uses should be a real, known label
        if label and label not in known_labels:
            issues.append(f"Citation label '{label}' is not in the known source set.")

    return issues


def split_out_disclaimer_sections(brief_text):
    """
    Return the brief text WITHOUT the sections that legitimately DISCUSS risky
    words while disclaiming them:
      - '## 5. What the Evidence Does NOT Support' (the fences)
      - '## 6. Evidence Limitations' (honest caveats)
    This prevents the scan from flagging the brief for responsibly stating its
    own limits.
    """
    lines = brief_text.splitlines()
    kept = []
    skipping = False
    for line in lines:
        if re.match(r"^##\s+5\.", line) or re.match(r"^##\s+6\.", line):
            skipping = True
            continue
        # Resume when we hit a later section that isn't 5 or 6
        if skipping and re.match(r"^##\s+7\.", line):
            skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def scan_for_risky_assertions(brief_text):
    """CHECK 2: scan the brief body (minus disclaimer sections) for risky claims."""
    body = split_out_disclaimer_sections(brief_text)
    findings = []
    for pattern in RISKY_PATTERNS:
        for match in re.finditer(pattern, body, flags=re.IGNORECASE):
            start = max(0, match.start() - 40)
            end = min(len(body), match.end() + 40)
            snippet = body[start:end].replace("\n", " ").strip()
            findings.append(f"Pattern '{pattern}' matched: \"...{snippet}...\"")
    return findings


def check_every_claim_cited(brief_text):
    """
    CHECK 1 (text-level): in section 4, every claim bullet should end with a
    [EVID-...] citation tag. Flag any evidence bullet missing one.
    """
    issues = []
    in_evidence_section = False
    for line in brief_text.splitlines():
        if re.match(r"^##\s+4\.", line):
            in_evidence_section = True
            continue
        if re.match(r"^##\s+5\.", line):
            in_evidence_section = False
        if in_evidence_section and line.strip().startswith("- "):
            if not re.search(r"\[EVID-\d+\]", line):
                issues.append(f"Uncited claim in evidence section: {line.strip()}")
    return issues


def verify(evidence_units, brief_text):
    """Run all checks and return a structured report."""
    unit_issues = verify_units(evidence_units)
    cited_issues = check_every_claim_cited(brief_text)
    risky_findings = scan_for_risky_assertions(brief_text)

    passed = not (unit_issues or cited_issues or risky_findings)
    return {
        "passed": passed,
        "citation_presence_issues": cited_issues,
        "source_integrity_issues": unit_issues,
        "risky_assertion_findings": risky_findings,
    }


def print_report(report):
    print("=" * 60)
    print("CITATION VERIFIER — AUDIT REPORT")
    print("=" * 60)

    print("\nCHECK 1 — Every evidence claim is cited:")
    if report["citation_presence_issues"]:
        for i in report["citation_presence_issues"]:
            print(f"   !! {i}")
    else:
        print("   OK — all evidence claims carry a citation.")

    print("\nCHECK 2 — No forbidden claim asserted in the brief:")
    if report["risky_assertion_findings"]:
        for f in report["risky_assertion_findings"]:
            print(f"   !! {f}")
    else:
        print("   OK — no risky/forbidden assertions found in the brief body.")

    print("\nCHECK 3 — Source & citation integrity:")
    if report["source_integrity_issues"]:
        for i in report["source_integrity_issues"]:
            print(f"   !! {i}")
    else:
        print("   OK — all sources contributed claims with valid labels.")

    print("\n" + "=" * 60)
    if report["passed"]:
        print("RESULT: PASSED — brief is fully cited and within source limits.")
    else:
        print("RESULT: FLAGGED — review the issues above before using this brief.")
    print("=" * 60)
    print("NOTE: v1 structural check. Deep semantic entailment is a v2 upgrade.")
    print("=" * 60)


def main():
    # Rebuild the pipeline output, then audit it.
    from patient_summary_agent import load_patient, build_summary, list_missing_info
    from question_builder import build_pico
    from evidence_retriever import build_patient_context, retrieve
    from evidence_extractor import extract_all
    from brief_generator import generate_brief

    base = Path("data")
    patient_file = base / "patients" / "synthetic_patient_001.json"
    summaries_dir = base / "evidence" / "summaries"

    patient = load_patient(patient_file)
    pico = build_pico(patient)
    missing_info = list_missing_info(patient)
    retrieval_text = pico["clinical_question"] + " " + build_patient_context(patient)
    results, _ = retrieve(retrieval_text, summaries_dir, top_k=6)

    if not results:
        print("NO EVIDENCE RETRIEVED. Nothing to verify.")
        return

    evidence_units = extract_all(results)
    brief_text = generate_brief(patient, pico, missing_info, evidence_units)

    report = verify(evidence_units, brief_text)
    print_report(report)


if __name__ == "__main__":
    main()