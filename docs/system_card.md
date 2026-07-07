# System Card — AI Clinical Evidence Agent

## Intended use

A portfolio prototype that demonstrates a governed, retrieval-augmented workflow
for organizing medical evidence on **synthetic** patient cases, for **clinician
review**. It summarizes a patient profile, retrieves curated evidence, compares
treatment options, and produces a cited, audited evidence brief.

## Not intended use

- Not for real clinical use, and not medical advice.
- Does not diagnose, prescribe, or select a final treatment.
- Does not use real or identifiable patient data.
- Does not connect to an electronic health record (EHR).
- Not for emergency, urgent, or time-sensitive medical situations.
- Not intended, validated, approved, or cleared for real clinical care.

## Data

- Synthetic patient profiles only, authored for this project.
- No protected health information (PHI) is used.
- Three synthetic knee-osteoarthritis cases spanning different scenarios
  (severe, moderate, and information-sparse).

## Evidence sources

- A small, curated library of user-authored plain-language summaries of real,
  publicly available medical sources (guidelines, reviews, trials, safety info).
- No copyrighted source text is reproduced; each card carries a citation and link.
- Each card declares explicit "claims allowed" and "claims NOT allowed" boundaries.

## Safety guardrails

- **Grounded output:** the brief is assembled from cited claims, not free-written.
- **Citation audit:** every brief is checked so that each medical claim carries a
  citation and no forbidden claim is asserted. Validated by injecting a known unsafe
  claim and confirming it is caught.
- **No invented success rates:** numerical figures appear only when a cited source
  explicitly supports them, with source context preserved.
- **Two safe-stops:** the system declines when no relevant evidence is found, and
  when the patient record is too incomplete to analyze responsibly.
- **Cautious language and a required clinician-review note** on every brief.

## Known limitations

- The evidence library is small and curated, not a live search of all literature;
  relevant evidence may be missing.
- Retrieval uses keyword/tag matching and cannot resolve synonyms or judge semantic
  relevance the way embeddings can.
- Citation verification is **structural** (is a claim cited? does it cross a declared
  fence?), not deep semantic entailment.
- Outputs demonstrate workflow and guardrails on synthetic data, not clinical accuracy.

## Human oversight

The system supports, and never replaces, clinical judgment. Every brief ends with a
required clinician-review statement. All output is intended for a licensed
clinician's independent review before any decision.

## Future work

- Add semantic retrieval with embeddings
- Add entailment-based citation verification
- Expand the curated evidence library
- Add more synthetic patient cases
- Add additional conditions beyond knee osteoarthritis
- Add clinician-reviewed evaluation scenarios