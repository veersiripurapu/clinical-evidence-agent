# Project Story — AI Clinical Evidence Agent

*A clinician-facing prototype that turns a synthetic patient case into a cited,
audited evidence brief — built to demonstrate responsible, human-in-the-loop
medical AI, not autonomous diagnosis.*

**🔗 Live demo:** https://clinical-evidence-agent.streamlit.app

---

## The question that started it

Doctors make treatment decisions by weighing a patient's current condition against
their medical history, prior treatments, available evidence, known risks, and gaps
in the record. That research and synthesis takes time.

The question I wanted to explore was:

**Could an AI agent help with the research-and-comparison legwork faster —
surfacing treatment options, evidence, risks, missing information, and uncertainty
— while leaving every decision to the clinician?**

The tempting version of this project would be "an AI that tells the doctor what to
do."

I deliberately did **not** build that.

That would be unsafe, and it misunderstands where AI can responsibly help. Instead,
I framed this as a **clinician-facing evidence-support prototype**. The agent
organizes evidence for independent clinician review. It does not diagnose,
prescribe, or choose a final treatment.

## Scope: one condition, done carefully

I limited v1 to **knee osteoarthritis**.

That condition has both conservative and surgical treatment pathways, clear
patient-specific considerations, and enough public guideline and literature
context to support a useful prototype.

Narrowing the scope let me focus on the harder problem: safe, grounded evidence
handling.

The goal was not to cover all of medicine. The goal was to build one small workflow
carefully enough that its safety design could be inspected and tested.

## The core design principle: honest by construction

The central risk with medical AI is that it can produce a confident but unsupported
statement — an invented statistic, an overgeneralized recommendation, or a claim no
source actually makes.

The architecture is built to make that structurally difficult.

- **The agent answers only from a curated evidence library**, not from open
  internet search or unsupported model memory. Each source is represented as a
  user-authored evidence card with citation metadata and a source link.
- **Every evidence card declares its own boundaries.** Each card includes explicit
  "claims allowed" and "claims NOT allowed" sections.
- **The brief is assembled from cited claims, not freely written as medical prose.**
  For v1, the generator acts as an assembler rather than an unconstrained author.
- **A citation verifier audits every brief.** It performs a structural check —
  confirming that medical claims carry evidence labels and that forbidden claims
  are not included. (Deep semantic verification — whether a source *truly* supports
  each specific claim — is noted as future work.)
- **The verifier was tested with a deliberately unsafe injected claim** such as a
  fabricated success rate and a directive treatment statement, confirming that the
  system flags unsafe output while passing clean briefs.

The design goal is not to hope the model behaves safely. The goal is to make the
safest behavior the default path.

## Decisions I made, and why

### Transparent retrieval over semantic search for v1

A vector search system would be more powerful, but I chose transparent keyword and
tag-based retrieval for the first version.

In a clinical context, auditability matters. I wanted to see exactly why a source
was retrieved: which terms matched, which card was selected, and how it flowed into
the final brief.

Semantic retrieval is a logical v2 upgrade, but the first version prioritizes
traceability over sophistication.

### Honest handling of success rates

Real treatment success rates depend on many factors: patient severity,
comorbidities, study population, follow-up period, outcome definition, and clinical
setting.

So the agent does not invent success rates.

It can only report a numerical figure when a cited source explicitly supports it,
and even then the brief must preserve the source context. Otherwise, it states that
a precise estimate cannot be responsibly provided from the available evidence.

### Two safe-stops

The system has two refusal paths.

The first safe-stop occurs when no relevant evidence is retrieved. In that case, the
agent does not generate a treatment comparison.

The second safe-stop occurs when the patient record itself is too incomplete. I
added this after testing a deliberately sparse synthetic patient. The test exposed a
real limitation: retrieval alone cannot tell the difference between a rich patient
case and a thin one. So I added a patient-completeness check before evidence review.

That became one of the most important safety behaviors in the project.

## What it does end to end

A synthetic patient profile goes in.

A structured, cited, audited evidence brief comes out.

The brief includes:

- synthetic patient summary
- clinical question
- missing or unclear information
- treatment-relevant evidence with citations
- explicit "what the evidence does NOT support" section
- evidence limitations
- required clinician-review note

Three test patients demonstrate three different outcomes:

1. A severe knee osteoarthritis case with failed conservative care and comorbidities
   produces a full evidence brief.
2. A moderate knee osteoarthritis case produces a different, more conservative-leaning
   brief.
3. A sparse patient record triggers a safe-stop and declines full evidence review.

An evaluation suite tests the core safety behaviors: citation coverage,
forbidden-claim detection, refusal to provide unsupported recommendations,
missing-information handling, no-evidence handling, and incomplete-patient safe-stop
behavior — all 8 tests passing (see `notebooks/06_evaluation.ipynb`).

## What I would do next

Future improvements would include:

- semantic retrieval using embeddings
- entailment-based citation checking to verify that each source truly supports each
  claim
- better source ranking based on patient context and record completeness
- broader evidence-library coverage
- additional conditions beyond knee osteoarthritis
- a stronger evaluation framework with clinician-reviewed test cases

## What this project is really about

This is not an "AI doctor."

It is a governed, auditable, human-in-the-loop evidence-support workflow.

The project demonstrates that the most important engineering in medical AI is not
simply generating polished text. It is building the guardrails: source control,
claim boundaries, citation verification, safe-stops, missing-information handling,
and clinician review.