# Risk and Safety Notes

## Core principle

This tool supports a clinician’s independent review. It does not replace clinical judgment.

The clinician always remains responsible for diagnosis, treatment decisions, patient counseling, and final care planning.

## Intended use

This prototype is intended to demonstrate how an AI system can organize synthetic patient context and retrieved medical evidence into a structured evidence brief.

It is for portfolio and educational purposes only.

## Data boundaries

- Only synthetic patient profiles are used.
- No real, identifiable patient data is used.
- No protected health information is used.
- No real EHR integration is included.
- No patient-facing clinical workflow is supported.

## Evidence and claims

- The agent should answer from retrieved evidence, not unsupported model memory.
- Every treatment benefit, risk, side effect, and numerical claim must cite a specific source.
- If a claim has no supporting source, it should be removed, flagged, or rewritten as uncertainty.
- Retrieved evidence may be incomplete, outdated, or not fully applicable to the synthetic patient profile.

## Success rates and numerical claims

The agent should not provide precise success rates unless the source explicitly reports:

- the outcome measured
- the patient population
- the intervention
- the follow-up period
- the reported numerical result

If those details are missing, the agent should state that a precise estimate cannot be responsibly provided from the available evidence.

## Missing information behavior

The agent should identify missing clinical details rather than guessing.

Examples may include:

- current medications
- allergies
- imaging severity
- BMI
- A1C or diabetes control
- surgical risk factors
- prior treatment response
- patient preferences

## Boundaries the agent will not cross

The agent will not:

- diagnose a real patient
- prescribe medication
- select a final treatment
- tell a patient what surgery to get
- provide emergency or urgent-care guidance
- replace a licensed clinician
- make insurance, employment, or coverage decisions
- generate unsupported success rates
- present synthetic results as real clinical outcomes

If asked what treatment or surgery a patient should get, the agent should redirect to clinician review and provide evidence-based options only.

## Emergency and urgent-care boundary

This prototype is not suitable for emergency, urgent, or time-sensitive medical situations.

Any urgent symptoms, rapid deterioration, or emergency concern requires immediate evaluation by qualified medical professionals.

## Human oversight

Every generated brief must include a clear clinician-review statement.

Example:

> This evidence brief is for clinician review only. It does not diagnose, prescribe, or recommend a final treatment. A licensed clinician must review the patient, evidence, risks, preferences, and local standards of care before making any decision.

## Responsible-use limitation

Because this project uses synthetic data and a limited evidence set, its output should be treated as a demonstration of workflow design, retrieval, citation handling, and safety guardrails — not as proof of clinical accuracy.