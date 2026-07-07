"""
question_builder.py

Pipeline step 2: turn a patient profile into a focused clinical question
using the PICO structure (Population, Intervention, Comparison, Outcome).

A sharp, structured question is what lets the later evidence retriever aim
at the right sources. We build it with PLAIN PYTHON from known facts.
"""

import json
from pathlib import Path


def load_patient(file_path):
    """Open a patient JSON file and return it as a Python dictionary."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_pico(patient):
    """Build a PICO-structured clinical question from the patient facts."""
    severity = patient["condition_severity"]
    condition = patient["condition"]
    tried_conservative = patient["conservative_care_attempted"]

    # Population: describe who this patient is, clinically
    population = f"adults with {severity} {condition}"
    if tried_conservative:
        population += " and persistent functional limitation after conservative therapy"

    # Intervention vs Comparison: the two paths a clinician would weigh
    intervention = "orthopedic evaluation for surgical management"
    comparison = "continued or optimized non-surgical management"

    # Outcomes: what a clinician cares about when comparing these paths
    outcomes = ["pain improvement", "physical function", "adverse events", "revision risk"]

    # Assemble the four parts into one readable question
    clinical_question = (
        f"For {population}, what are the benefits, risks, and evidence "
        f"limitations of {intervention} compared with {comparison}, "
        f"with respect to {', '.join(outcomes)}?"
    )

    return {
        "clinical_question": clinical_question,
        "population": population,
        "interventions": [intervention, comparison],
        "outcomes": outcomes,
    }


def main():
    patient_file = Path("data") / "patients" / "synthetic_patient_001.json"
    patient = load_patient(patient_file)
    pico = build_pico(patient)

    print("=" * 60)
    print(f'CLINICAL QUESTION FOR: {patient["patient_id"]}')
    print("=" * 60)
    print("\nQUESTION")
    print("-" * 60)
    print(pico["clinical_question"])

    print("\nPICO BREAKDOWN")
    print("-" * 60)
    print(f'  Population:    {pico["population"]}')
    print(f'  Interventions: {pico["interventions"][0]}')
    print(f'                 vs {pico["interventions"][1]}')
    print(f'  Outcomes:      {", ".join(pico["outcomes"])}')

    print("\n" + "=" * 60)
    print("NOTE: Synthetic data. Question is for evidence retrieval, not a decision.")
    print("=" * 60)


if __name__ == "__main__":
    main()