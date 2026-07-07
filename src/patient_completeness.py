"""
patient_completeness.py

A content-aware safe-stop. BEFORE the pipeline builds a brief, this checks how
much real information we actually have about the patient. If the record is too
sparse, the pipeline should decline a full evidence review rather than imply we
know more than we do.

This is distinct from the evidence safe-stop (which fires when NO evidence is
retrieved). This one fires when there is not enough PATIENT information to
responsibly proceed.

Plain, transparent scoring — no AI.
"""

# The key fields we'd want present to do a meaningful review.
# (field_path, human_label) — dotted paths reach into nested objects.
KEY_FIELDS = [
    ("condition_severity", "Condition severity"),
    ("symptom_summary.duration_years", "Symptom duration"),
    ("symptom_summary.reported_pain_severity", "Pain severity"),
    ("prior_treatments", "Prior treatment history"),
    ("comorbidities", "Comorbidities"),
    ("current_medications", "Current medications"),
    ("allergies", "Allergies"),
    ("imaging_summary.finding", "Imaging findings"),
]

# Values that LOOK filled but carry no real information.
PLACEHOLDER_SIGNALS = [
    "not documented", "not available", "none on file", "not recorded",
    "unclear", "unknown", "history unclear",
]


def _get_nested(patient, dotted_path):
    """Follow a path like 'symptom_summary.finding' into nested dicts."""
    value = patient
    for part in dotted_path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def _is_meaningful(value):
    """Return True only if this value carries real information."""
    if value is None:
        return False
    if isinstance(value, list):
        if len(value) == 0:
            return False
        # A list of only placeholder strings doesn't count
        for item in value:
            if isinstance(item, str) and _looks_placeholder(item):
                continue
            return True   # found at least one real item
        return False
    if isinstance(value, str):
        return not _looks_placeholder(value)
    # numbers, etc.
    return True


def _looks_placeholder(text):
    """True if a string is empty or a known placeholder."""
    t = text.strip().lower()
    if t == "":
        return True
    return any(signal in t for signal in PLACEHOLDER_SIGNALS)


def assess_completeness(patient, threshold=0.5):
    """
    Score how complete a patient record is.

    Returns a dict:
      present / total / score / sufficient / present_fields / missing_fields
    'sufficient' is True when score >= threshold.
    """
    present_fields = []
    missing_fields = []

    for path, label in KEY_FIELDS:
        value = _get_nested(patient, path)
        if _is_meaningful(value):
            present_fields.append(label)
        else:
            missing_fields.append(label)

    total = len(KEY_FIELDS)
    present = len(present_fields)
    score = present / total if total else 0.0

    return {
        "present": present,
        "total": total,
        "score": score,
        "sufficient": score >= threshold,
        "present_fields": present_fields,
        "missing_fields": missing_fields,
    }


def main():
    import json
    from pathlib import Path

    patients_dir = Path("data") / "patients"
    print("=" * 60)
    print("PATIENT COMPLETENESS CHECK (threshold = 50%)")
    print("=" * 60)

    for pf in sorted(patients_dir.glob("synthetic_patient_*.json")):
        patient = json.loads(pf.read_text(encoding="utf-8"))
        result = assess_completeness(patient, threshold=0.5)
        verdict = "SUFFICIENT" if result["sufficient"] else "INSUFFICIENT -> decline full review"
        print(f"\n{patient['patient_id']}:")
        print(f"  Completeness: {result['present']}/{result['total']} "
              f"({result['score']*100:.0f}%)  ->  {verdict}")
        if not result["sufficient"]:
            print(f"  Missing: {', '.join(result['missing_fields'])}")


if __name__ == "__main__":
    main()