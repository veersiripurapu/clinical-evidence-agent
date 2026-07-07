"""
patient_summary_agent.py

Pipeline step 1: read a synthetic patient JSON file and turn it into a
clean, human-readable clinical summary plus a list of missing information.

This component uses PLAIN PYTHON, not an AI model. The patient data is
already structured, so we only reorganize known facts. Using an AI model
here would risk inventing details that aren't in the file — which we never
want in a medical tool.
"""

import json
from pathlib import Path

def plural(value, singular, plural_form):
    """Return the singular or plural word depending on the value (1 vs many)."""
    return singular if value == 1 else plural_form

def load_patient(file_path):
    """Open a patient JSON file and return it as a Python dictionary."""
    with open(file_path, "r", encoding="utf-8") as f:
        patient = json.load(f)
    return patient


def build_summary(patient):
    """Turn the patient dictionary into a readable clinical summary."""
    symptom = patient["symptom_summary"]

    # Turn the list of prior treatments into one readable phrase
    prior = "; ".join(
        f'{t["treatment"]} ({t["response"]})' for t in patient["prior_treatments"]
    )
    comorbidities = ", ".join(patient["comorbidities"])

    summary = (
        f'{patient["age"]}-year-old {patient["sex"]} with '
        f'{patient["condition_severity"]} {patient["condition"]}. '
        f'Chief concern: {patient["chief_concern"].lower()}. '
        f'Primary symptom is {symptom["primary_symptom"].lower()} '
       f'for {symptom["duration_years"]} '
        f'{plural(symptom["duration_years"], "year", "years")}, worsening over the past '
        f'{symptom["worsening_period_months"]} '
        f'{plural(symptom["worsening_period_months"], "month", "months")} '
        f'(reported severity: {symptom["reported_pain_severity"]}). '
        f'Prior treatments: {prior}. '
        f'Comorbidities: {comorbidities}. '
        f'Imaging: {patient["imaging_summary"]["finding"]}.'
    )
    return summary


def list_missing_info(patient):
    """Return the list of missing or unclear information."""
    return patient["missing_or_unclear_information"]


def main():
    # Build the file path safely so it works on any operating system
    patient_file = Path("data") / "patients" / "synthetic_patient_001.json"

    patient = load_patient(patient_file)

    print("=" * 60)
    print(f'PATIENT: {patient["patient_id"]}')
    print("=" * 60)

    print("\nCLINICAL SUMMARY")
    print("-" * 60)
    print(build_summary(patient))

    print("\nMISSING OR UNCLEAR INFORMATION")
    print("-" * 60)
    for item in list_missing_info(patient):
        print(f"  - {item}")

    print("\n" + "=" * 60)
    print("NOTE: Synthetic data. For clinician review only. Not medical advice.")
    print("=" * 60)


if __name__ == "__main__":
    main()