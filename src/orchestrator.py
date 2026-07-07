"""
orchestrator.py

The conductor. Defines the ONE authoritative run of the pipeline, start to
finish, so every other entry point (app, notebook, tests) calls this instead
of re-wiring the chain itself.

    load patient
        -> completeness check (content-aware safe-stop)
        -> summarize
        -> build clinical question
        -> retrieve evidence (patient-aware, safe-stop on empty)
        -> extract structured, fenced, cited units
        -> generate the clinician brief
        -> verify the brief (citation + fence audit)

Returns everything a caller might want, as one tidy result dict.

The pipeline can end in three ways:
    "ok"                        -> a verified brief was produced
    "no_evidence"               -> no evidence matched (evidence safe-stop)
    "insufficient_patient_data" -> too little patient info (content safe-stop)
"""

from pathlib import Path

from patient_summary_agent import load_patient, build_summary, list_missing_info
from question_builder import build_pico
from evidence_retriever import build_patient_context, retrieve
from evidence_extractor import extract_all
from brief_generator import generate_brief
from citation_verifier import verify
from patient_completeness import assess_completeness


def run_pipeline(patient_file, summaries_dir=None, top_k=6):
    """
    Run the full clinical-evidence pipeline for one patient file.

    Returns a dict:
      {
        "status": "ok" | "no_evidence" | "insufficient_patient_data",
        "patient": <patient dict>,
        "pico": <question dict> or None,
        "missing_info": [...],
        "completeness": <completeness report>,
        "evidence_units": [...],
        "brief_markdown": "<the full brief>" or None,
        "audit": <verifier report> or None,
      }
    """
    patient_file = Path(patient_file)
    if summaries_dir is None:
        summaries_dir = Path("data") / "evidence" / "summaries"

    # 1. Patient
    patient = load_patient(patient_file)
    missing_info = list_missing_info(patient)

    # 1b. Content-aware safe-stop: is there enough PATIENT information?
    completeness = assess_completeness(patient, threshold=0.5)
    if not completeness["sufficient"]:
        return {
            "status": "insufficient_patient_data",
            "patient": patient,
            "pico": None,
            "missing_info": missing_info,
            "completeness": completeness,
            "evidence_units": [],
            "brief_markdown": None,
            "audit": None,
        }

    # 2. Clinical question
    pico = build_pico(patient)

    # 3. Retrieve (patient-aware)
    retrieval_text = pico["clinical_question"] + " " + build_patient_context(patient)
    results, retrieval_terms = retrieve(retrieval_text, summaries_dir, top_k=top_k)

    # Evidence safe-stop: no evidence -> no brief. The conductor won't fake a song.
    if not results:
        return {
            "status": "no_evidence",
            "patient": patient,
            "pico": pico,
            "missing_info": missing_info,
            "completeness": completeness,
            "evidence_units": [],
            "brief_markdown": None,
            "audit": None,
        }

    # 4. Extract structured, fenced units
    evidence_units = extract_all(results)

    # 5. Generate the brief
    brief_markdown = generate_brief(patient, pico, missing_info, evidence_units)

    # 6. Audit the brief
    audit = verify(evidence_units, brief_markdown)

    return {
        "status": "ok",
        "patient": patient,
        "pico": pico,
        "missing_info": missing_info,
        "completeness": completeness,
        "evidence_units": evidence_units,
        "brief_markdown": brief_markdown,
        "audit": audit,
    }


def save_brief(result, out_dir="outputs"):
    """Save the brief to outputs/ and return the path (or None if no brief)."""
    if result["status"] != "ok":
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    pid = result["patient"]["patient_id"]
    out_path = out_dir / f"evidence_brief_{pid}.md"
    out_path.write_text(result["brief_markdown"], encoding="utf-8")
    return out_path


def main():
    patient_file = Path("data") / "patients" / "synthetic_patient_001.json"
    result = run_pipeline(patient_file)

    print("=" * 60)
    print(f"PIPELINE RUN — {result['patient']['patient_id']}")
    print("=" * 60)
    print(f"Status: {result['status']}")

    # Content-aware safe-stop
    if result["status"] == "insufficient_patient_data":
        c = result["completeness"]
        print(f"\nINSUFFICIENT PATIENT DATA "
              f"({c['present']}/{c['total']} key fields present).")
        print("Full evidence review declined. Missing key fields:")
        for f in c["missing_fields"]:
            print(f"  - {f}")
        print("\nComplete the patient record before generating a brief.")
        return

    # Evidence safe-stop
    if result["status"] == "no_evidence":
        print("\nNo evidence retrieved. Brief not generated (safe-stop).")
        return

    # Normal path
    print(f"Evidence sources used: {len(result['evidence_units'])}")
    audit = result["audit"]
    print(f"Audit result: {'PASSED' if audit['passed'] else 'FLAGGED'}")

    out_path = save_brief(result)
    print(f"Brief saved to: {out_path}")

    print("\n" + "=" * 60)
    print("Full pipeline ran from a single call: run_pipeline(patient_file)")
    print("=" * 60)


if __name__ == "__main__":
    main()