"""
app.py — Streamlit front end for the Clinical Evidence Agent.

A thin dashboard over the pipeline: pick a synthetic patient, run the pipeline,
and view the result. All clinical/evidence logic lives in src/.
"""

import json
import sys
from pathlib import Path

import streamlit as st

# Resolve project paths safely
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
PATIENTS_DIR = BASE_DIR / "data" / "patients"

# Make src/ modules importable
sys.path.insert(0, str(SRC_DIR))

from orchestrator import run_pipeline, save_brief  # noqa: E402
from qa_agent import answer_question


st.set_page_config(page_title="Clinical Evidence Agent", layout="wide")

st.title("AI Clinical Evidence Agent")
st.caption("Treatment-option review for clinician use — synthetic data only.")

st.warning(
    "**For clinician review only. Synthetic data. Not medical advice.** "
    "This prototype does not diagnose, prescribe, or recommend a final treatment. "
    "A licensed clinician must review all output."
)

# Initialize session state
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

if "selected_patient_file" not in st.session_state:
    st.session_state.selected_patient_file = None


# -----------------------------
# Sidebar: patient selection
# -----------------------------
st.sidebar.header("Select a synthetic patient")

patient_files = sorted(PATIENTS_DIR.glob("synthetic_patient_*.json"))

if not patient_files:
    st.error(
        "No synthetic patient files found. Add JSON files under "
        "`data/patients/` with names like `synthetic_patient_001.json`."
    )
    st.stop()

options = {}

for pf in patient_files:
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
        patient_id = data.get("patient_id", pf.stem)
        case_title = data.get("case_title", "Untitled synthetic case")
        label = f"{patient_id} — {case_title}"
        options[label] = pf
    except Exception as exc:
        st.sidebar.warning(f"Skipped invalid patient file: {pf.name} ({exc})")

if not options:
    st.error("No valid synthetic patient files could be loaded.")
    st.stop()

choice = st.sidebar.selectbox("Patient case", list(options.keys()))
selected_patient_file = options[choice]

run_clicked = st.sidebar.button("Generate Evidence Brief", type="primary")

# Optional reset button
if st.sidebar.button("Clear current result"):
    st.session_state.pipeline_result = None
    st.session_state.selected_patient_file = None


# -----------------------------
# Run pipeline
# -----------------------------
if run_clicked:
    with st.spinner("Running pipeline..."):
        try:
            result = run_pipeline(selected_patient_file)
            st.session_state.pipeline_result = result
            st.session_state.selected_patient_file = selected_patient_file
        except Exception as exc:
            st.session_state.pipeline_result = None
            st.error("Pipeline failed before producing a brief.")
            st.exception(exc)
            st.stop()


# -----------------------------
# Main display
# -----------------------------
result = st.session_state.pipeline_result

if result is None:
    st.info("Pick a patient in the sidebar and click **Generate Evidence Brief**.")
    st.stop()

patient = result.get("patient", {})
status = result.get("status", "unknown")

st.subheader("Selected synthetic patient")
st.write(f"**Patient ID:** {patient.get('patient_id', 'Unknown')}")
st.write(f"**Case:** {patient.get('case_title', 'Untitled synthetic case')}")

# Completeness metric
comp = result.get("completeness")

if comp:
    present = comp.get("present", 0)
    total = comp.get("total", 0)
    score = comp.get("score", 0)

    st.metric(
        "Patient record completeness",
        f"{present}/{total} key fields ({score * 100:.0f}%)",
    )


# -----------------------------
# Outcome 1: insufficient patient data
# -----------------------------
if status == "insufficient_patient_data":
    st.error(
        "**Insufficient patient data — full evidence review declined.**\n\n"
        "There is not enough documented information about this patient to "
        "responsibly generate a treatment-option comparison."
    )

    st.subheader("Missing key fields")

    missing_fields = []
    if comp:
        missing_fields = comp.get("missing_fields", [])

    if missing_fields:
        for field in missing_fields:
            st.write(f"- {field}")
    else:
        st.write("Missing fields were not provided by the pipeline output.")

    st.info("Complete the patient record, then re-run the pipeline.")


# -----------------------------
# Outcome 2: no evidence retrieved
# -----------------------------
elif status == "no_evidence":
    st.error(
        "**No matching evidence found.** The system did not retrieve any evidence "
        "for this case, so no clinical evidence brief was generated."
    )

    st.info(
        "Add relevant evidence cards to the curated evidence library or revise the "
        "clinical question, then re-run the pipeline."
    )


# -----------------------------
# Outcome 3: full brief produced
# -----------------------------
elif status == "ok":
    audit = result.get("audit", {})
    audit_passed = audit.get("passed", False)

    if audit_passed:
        st.success("Citation audit: PASSED — every claim cited, no forbidden claims.")
    else:
        st.error("Citation audit: FLAGGED — review issues before use.")

    brief_markdown = result.get("brief_markdown", "")

    if not brief_markdown:
        st.error("Pipeline status says a brief was generated, but no Markdown brief was returned.")
        st.stop()

    out_path = save_brief(result)

    st.download_button(
        "Download brief (Markdown)",
        data=brief_markdown,
        file_name=out_path.name,
        mime="text/markdown",
    )

    with st.expander("Audit details"):
        st.json(audit)

        st.divider()
        st.markdown(brief_markdown)

        st.divider()
        st.subheader("Ask an evidence question")
        st.caption("Answers are drawn only from the selected synthetic patient and the curated evidence cards. It will not diagnose, prescribe, or choose a treatment.")
        user_question = st.text_input("Your question", placeholder="e.g. Why is A1C important for this patient?", key="qa_input")
        if st.button("Answer question"):
            qa = answer_question(user_question, result)
            st.markdown(qa["answer_markdown"])
            if qa.get("matched_claims"):
                with st.expander("Evidence claims used in this answer"):
                    st.json(qa["matched_claims"])

# -----------------------------
# Unknown status
# -----------------------------
else:
    st.error(f"Unknown pipeline status: `{status}`")
    st.write("Review the output from `run_pipeline()`.")
    st.json(result)