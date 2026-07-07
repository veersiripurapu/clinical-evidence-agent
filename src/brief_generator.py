"""
brief_generator.py

Pipeline step: assemble the final clinician-facing evidence brief.

Key design principle: this is an ASSEMBLER, not an author. Every piece of
medical content comes from a fenced, cited claim that the extractor pulled
from a verified evidence card. The generator arranges these pre-approved,
pre-cited pieces into a structured document. It cannot introduce an unsourced
claim, because it only has sourced claims to work with.

Outputs to BOTH the terminal and a saved Markdown file in outputs/.
"""

from pathlib import Path
from datetime import date

# Reuse the components we already built (the LEGO-studs paying off)
from patient_summary_agent import load_patient, build_summary, list_missing_info
from question_builder import build_pico
from evidence_retriever import build_patient_context, retrieve
from evidence_extractor import extract_all


def generate_brief(patient, pico, missing_info, evidence_units):
    """Assemble the evidence brief as a Markdown string."""
    lines = []

    # 1. Safety header
    lines.append("# Clinical Evidence Brief")
    lines.append("")
    lines.append(f"*Generated: {date.today().isoformat()} | Patient: "
                 f"{patient['patient_id']} (SYNTHETIC)*")
    lines.append("")
    lines.append("> **Intended use:** This brief is for clinician review only. "
                 "It uses synthetic data. It does not diagnose, prescribe, or "
                 "recommend a final treatment. A licensed clinician must review "
                 "everything below before any decision.")
    lines.append("")

    # 2. Patient summary
    lines.append("## 1. Patient Summary")
    lines.append("")
    lines.append(build_summary(patient))
    lines.append("")

    # 3. Clinical question
    lines.append("## 2. Clinical Question")
    lines.append("")
    lines.append(pico["clinical_question"])
    lines.append("")

    # 4. Missing information (before the evidence, on purpose)
    lines.append("## 3. Missing or Unclear Information")
    lines.append("")
    lines.append("_The following would be needed for fuller clinician review:_")
    lines.append("")
    for item in missing_info:
        lines.append(f"- {item}")
    lines.append("")

    # 5. Evidence and treatment options (fenced, cited claims)
    lines.append("## 4. Evidence for Clinician Review")
    lines.append("")
    lines.append("_Each point below is drawn from a curated, cited source. "
                 "Nothing here is a treatment recommendation._")
    lines.append("")
    for u in evidence_units:
        lines.append(f"### {u['title']}  \n`[{u['citation_label']}]`")
        lines.append("")
        if u["allowed_claims"]:
            lines.append("**Supported by this source:**")
            for claim in u["allowed_claims"]:
                lines.append(f"- {claim} `[{u['citation_label']}]`")
            lines.append("")

    # 6. What the evidence does NOT support (the fences, shown openly)
    lines.append("## 5. What the Evidence Does NOT Support")
    lines.append("")
    lines.append("_Explicit limits declared by the sources themselves:_")
    lines.append("")
    for u in evidence_units:
        if u["not_allowed_claims"]:
            for claim in u["not_allowed_claims"]:
                lines.append(f"- {claim} `[{u['citation_label']}]`")
    lines.append("")

    # 7. Evidence limitations
    lines.append("## 6. Evidence Limitations")
    lines.append("")
    lines.append("- This brief draws from a small, curated evidence library, "
                 "not a live search of all literature. Relevant evidence may be missing.")
    lines.append("- Retrieved sources may not perfectly match this synthetic patient.")
    lines.append("- Reported outcomes vary by population, severity, and follow-up period.")
    lines.append("- No precise success rate is provided unless a source explicitly reports one.")
    lines.append("")

    # 8. Citations
    lines.append("## 7. Citations")
    lines.append("")
    for u in evidence_units:
        cite = u.get("citation") or u["title"]
        url = u.get("url", "")
        lines.append(f"- `[{u['citation_label']}]` {cite} {url}".rstrip())
    lines.append("")

    # 9. Clinician-review note
    lines.append("## 8. Clinician Review Required")
    lines.append("")
    lines.append("This evidence brief is not a treatment recommendation. A licensed "
                 "clinician must review the patient, evidence, risks, preferences, and "
                 "local standards of care before making any decision.")
    lines.append("")

    return "\n".join(lines)


def main():
    base = Path("data")
    patient_file = base / "patients" / "synthetic_patient_001.json"
    summaries_dir = base / "evidence" / "summaries"

    # Run the full pipeline
    patient = load_patient(patient_file)
    pico = build_pico(patient)
    missing_info = list_missing_info(patient)

    retrieval_text = pico["clinical_question"] + " " + build_patient_context(patient)
    results, _ = retrieve(retrieval_text, summaries_dir, top_k=6)

    # Safe-stop: no evidence -> no brief
    if not results:
        print("NO EVIDENCE RETRIEVED. Brief not generated. "
              "Add evidence cards or revise the question.")
        return

    evidence_units = extract_all(results)
    brief_md = generate_brief(patient, pico, missing_info, evidence_units)

    # Print to terminal
    print(brief_md)

    # Save to outputs/
    out_dir = Path("outputs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"evidence_brief_{patient['patient_id']}.md"
    out_path.write_text(brief_md, encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"SAVED: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()