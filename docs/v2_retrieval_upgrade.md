# v2 — Retrieval Upgrade: Hybrid Semantic Retrieval with a Clinical-Relevance Layer

*How growing the evidence library exposed a real clinical retrieval failure, why semantic search alone did not fix it, and what actually did.*

This document is the story of the v2 retrieval work. It is written to be honest
about what worked, what did not, and why — including a negative result that turned
out to be more instructive than a clean success would have been.

---

## 1. The starting point: retrieval wasn't actually doing anything

After v1 shipped, I profiled the system across all three patients to decide where a
v2 improvement would actually pay off, rather than guessing. The profiling revealed
something I hadn't noticed: with only six evidence cards and a retrieval cap of six,
**every patient retrieved all six cards, every time.** The retriever ranked them, but
it never *selected* — there was nothing to leave out.

That reframed the obvious next step. The "impressive" move would have been to jump
straight to semantic retrieval with embeddings. But semantic search only matters when
there are many candidates and choosing well among them is a real problem. With six
cards and six slots, swapping in embeddings would have produced *identical output* —
sophisticated engineering with zero observable effect. That is the definition of
premature optimization.

**Conclusion:** the real constraint wasn't retrieval quality — it was library size.
So the highest-leverage first move was to grow the evidence library, which would make
retrieval a genuine selection problem *and* make any retrieval improvement measurable.

## 2. Growing the library — and immediately exposing a failure

I expanded the curated library from 6 to 11 cards, each an original, verified summary
of a real source with explicit claim fences (the same discipline as v1). The new cards
filled real gaps in the knee-osteoarthritis decision path: arthroscopy (notably *not*
recommended — a card whose main claim is a negative recommendation), weight loss as a
treatment, partial vs. total knee replacement tradeoffs, exercise therapy specifics,
and topical NSAIDs as a lower-risk alternative to oral NSAIDs.

With 11 cards and a cap of six, retrieval finally had to *choose* — and it immediately
failed in a clinically meaningful way.

For **SYN-KOA-001** — a 62-year-old woman with type 2 diabetes, hypertension, and
obesity, taking oral ibuprofen — the keyword retriever **dropped the topical-NSAID
card (EVID-011).** That card is arguably the single most actionable piece of evidence
for this specific patient: topical NSAIDs offer similar pain relief with fewer systemic
adverse effects and are specifically recommended for older patients with exactly her
comorbidities. The retriever also dropped the arthroscopy ("not recommended") card and,
for this surgical-risk patient, the total-knee-replacement risks card.

**Why it failed:** the topical-NSAID card's tags include "topical NSAIDs," "diclofenac,"
"alternative to oral NSAIDs." The patient's record contains "ibuprofen." A keyword
matcher has no idea that *ibuprofen is an oral NSAID* and that *topical NSAIDs are the
relevant alternative.* It cannot make that connection, because it matches strings, not
meaning.

This was the concrete, clinically-consequential failure that justified a retrieval
upgrade — not "embeddings are better in theory," but "my retriever missed the safest
medication alternative for a diabetic patient on ibuprofen, because it couldn't connect
'ibuprofen' to 'topical NSAID.'"

## 3. The negative result: semantic retrieval alone did NOT fix it

I built a hybrid retriever that blends the existing transparent keyword score with a
semantic-similarity score from a local sentence-transformer model
(`all-MiniLM-L6-v2`). I chose hybrid over pure semantic deliberately: pure embeddings
would sacrifice the auditability that the whole project depends on — a clinician can
read "matched: diabetes, obesity," but not "similarity 0.83."

**The first attempt did not fix the failure.** Embedding one large blob (the full
clinical question plus all patient context) produced an undiscriminating vector: every
knee-OA card scored roughly 0.47–0.74, with almost no spread. The model correctly saw
that every card was "about knee osteoarthritis," but couldn't distinguish the card that
*specifically* mattered for this patient from the ones that were merely on-topic.

I then tried **faceted queries** — generating several narrow sub-queries from the
patient's actual situation (medications, comorbidities, treatment history, severity)
and scoring each card against every facet, keeping its best match. This gave the
semantic scores more spread, but it *still* didn't surface the topical-NSAID card. The
purpose-built medication-safety facet matched the *oral* NSAID safety card instead —
which, honestly, is not an unreasonable judgment for a model that sees two similar cards
and picks the more textually similar one.

**The lesson — and it is the most valuable finding of the v2 work:**

> A general-purpose embedding model does not know medicine. It can match topics, but it
> cannot make a *clinical inference* like "this patient is *on* oral NSAIDs and has
> comorbidities, therefore surface the safer *alternative*." **Semantic similarity is
> not clinical relevance.** That inference requires domain knowledge the model simply
> does not have.

This is a more sophisticated result than a success would have been. It is exactly the
kind of thing a healthcare-AI team needs someone to understand: that reaching for the
fashionable technique and measuring that it *doesn't* solve the real problem is itself
the important work.

## 4. What actually fixed it: an explicit clinical-relevance layer

Since the missing relevance was *clinical*, not *semantic*, I encoded it explicitly —
as auditable domain rules rather than opaque model behavior. Two mechanisms:

**Clinical boost rules.** Small, explicit, reviewable rules that raise a card's score
when it is specifically relevant to the patient's situation. For example: *if the
patient is on an oral NSAID AND has diabetes / hypertension / kidney or cardiovascular
risk factors → boost the topical-NSAID alternative card.* Each rule carries a
human-readable reason that appears in the retrieval output. Notably, writing these
rules down is *more* transparent than an embedding score, not less — a clinician can
read and challenge every rule.

**Category-coverage guarantee.** Ensure the retrieved set spans the treatment decision
space (conservative / medication / surgical / surgical-risk), so a clinically-essential
category can't be crowded out by several cards from the same category.

With this layer in place, SYN-KOA-001's retrieved set now correctly includes the
topical-NSAID card (via the oral-NSAID + comorbidity rule), the total-knee-replacement
risks card, and the surgical-risk optimization card — and every inclusion is
explainable, either by keyword match, semantic relevance, a named clinical boost, or a
coverage guarantee.

The retrieval limit was also raised from 6 to 8, which is honest for a richer library:
a brief drawing on 11 available sources should be allowed to cite more than six.

## 5. Verification: the safety suite still passes

A retrieval overhaul is exactly the kind of change that can quietly break something
downstream. After wiring the new retriever into the pipeline, I re-ran the 8-test
safety suite. **All eight tests still pass** — including citation coverage (every one
of the new claims is cited), citation integrity (all new source tags resolve, "8 tags
used, 0 orphans"), and forbidden-claim detection. A retrieval change that passes every
safety test is the difference between "I upgraded retrieval" and "I upgraded retrieval
and proved I didn't break the guardrails doing it."

## 6. Deployment: the risk that didn't materialize

I flagged a real deployment risk up front: `sentence-transformers` pulls in PyTorch,
which is large, and Streamlit Community Cloud has memory limits. The system was built
to **degrade gracefully** — if the embedding model can't load, retrieval falls back to
keyword-only rather than crashing.

The honest outcome: the deployment *succeeded*, and the semantic layer runs live. The
public brief for SYN-KOA-001 now surfaces the topical-NSAID evidence, on the internet,
in the free tier. The small MiniLM model fit within the available resources. The
graceful-degradation path remains as a safety net, but it wasn't needed.

## 7. The v2 arc, and why it's the strongest part of the project

The full sequence:

1. **Profiled** the system and found retrieval wasn't actually selecting anything.
2. **Grew** the evidence library — which made retrieval a real problem and exposed a
   concrete clinical failure.
3. **Tried** hybrid semantic retrieval — the fashionable fix.
4. **Measured** that it did *not* solve the failure.
5. **Understood** why (semantic similarity ≠ clinical relevance).
6. **Built** an explicit, auditable clinical-relevance layer that did solve it.
7. **Verified** the safety suite still passes.
8. **Shipped** it, and confirmed the fix reaches the live public brief.

That arc — profile, discover, try, measure failure, understand, build, verify, ship —
demonstrates something more valuable than any single technique: engineering judgment.
Choosing the transparent approach over the flashy one; growing the library before
optimizing retrieval; reaching for embeddings and then honestly reporting that they
weren't enough; and encoding domain knowledge explicitly so the system stays auditable.

## 8. What I'd still improve

- The arthroscopy ("not recommended") card is retrieved for some patients but not
  reliably for the surgical-candidate patient; the coverage rule treats the broad
  "surgical" category as satisfied by other cards. A finer-grained coverage notion
  (e.g. "always include at least one *not-recommended* option when surgery is discussed")
  would close this.
- The clinical boost rules are hand-authored and specific to knee OA; scaling to more
  conditions would need a more systematic way to encode clinical relevance.
- Entailment-based citation verification remains the deepest outstanding safety upgrade.
- A clinician-reviewed evaluation set would strengthen the safety suite beyond synthetic
  self-tests.

---

*The headline of v2 is not "I added semantic search." It is: I found a real clinical
retrieval failure, discovered that semantic search alone didn't fix it, understood why,
and built an auditable clinical-relevance layer that did — without breaking a single
safety guardrail, and while keeping every retrieval decision explainable.*