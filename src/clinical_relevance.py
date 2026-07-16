"""
clinical_relevance.py

A clinical-relevance layer on top of retrieval.

WHY THIS EXISTS:
Semantic similarity answers "is this card about a similar topic?"
Clinical relevance answers "does this card matter for THIS patient's situation?"
Those are different questions. A general-purpose embedding model has no medical
knowledge — it cannot infer that a patient ON oral NSAIDs WITH diabetes and
hypertension should be shown the topical-NSAID *alternative*. That inference is
domain knowledge, so we encode it explicitly.

Two mechanisms:
  1. BOOST RULES  - explicit, auditable clinical rules that raise a card's score
                    when it is specifically relevant to this patient's situation.
  2. COVERAGE     - guarantee the retrieved set spans the treatment decision space,
                    so clinically-essential categories cannot be crowded out.

Writing these rules down is MORE transparent than an opaque similarity score, not
less — a clinician can read and challenge every rule.
"""


# Which treatment category each card belongs to (for coverage).
CARD_CATEGORY = {
    "EVID-001": "conservative",
    "EVID-002": "surgical_risk",
    "EVID-003": "surgical",
    "EVID-004": "medication",
    "EVID-005": "injection",
    "EVID-006": "surgical_risk",
    "EVID-007": "surgical",
    "EVID-008": "conservative",
    "EVID-009": "surgical",
    "EVID-010": "conservative",
    "EVID-011": "medication",
}

# Categories we always want represented in a full evidence brief.
REQUIRED_CATEGORIES = ["conservative", "medication", "surgical", "surgical_risk"]


def _has_any(values, keywords):
    """True if any keyword appears in any of the values (case-insensitive)."""
    text = " ".join(str(v).lower() for v in values)
    return any(k in text for k in keywords)


def clinical_boosts(patient):
    """
    Return {source_id: (boost, reason)} for cards specifically relevant to this
    patient's clinical situation. Each rule is explicit and reviewable.
    """
    boosts = {}

    meds = patient.get("current_medications", [])
    comorbidities = patient.get("comorbidities", [])
    priors = [t.get("treatment", "") for t in patient.get("prior_treatments", [])]
    missing = patient.get("missing_or_unclear_information", [])
    severity = str(patient.get("condition_severity", "")).lower()

    on_oral_nsaid = _has_any(meds, ["ibuprofen", "naproxen", "nsaid", "diclofenac oral"])
    nsaid_risk = _has_any(comorbidities, ["diabetes", "hypertension", "kidney", "renal",
                                          "cardiovascular", "heart"]) \
        or _has_any(missing, ["kidney", "renal", "cardiovascular"])

    # RULE 1 — Patient is on an oral NSAID AND has risk factors for NSAID harm.
    # A safer alternative is highly relevant. An embedding model cannot infer this.
    if on_oral_nsaid and nsaid_risk:
        boosts["EVID-011"] = (0.45,
            "Patient takes an oral NSAID and has comorbidities/gaps that raise NSAID risk; "
            "topical NSAID alternative is clinically relevant.")
        boosts["EVID-004"] = (0.20,
            "Patient takes an oral NSAID with risk factors; oral NSAID safety is relevant.")

    # RULE 2 — Surgical-risk comorbidities present.
    if _has_any(comorbidities, ["diabetes", "obes", "hypertension"]):
        boosts["EVID-006"] = (0.30,
            "Patient has comorbidities that raise surgical risk; preoperative optimization "
            "is clinically relevant.")

    # RULE 3 — Severe disease with failed conservative care: surgical evaluation
    # AND the risks of surgery both become relevant.
    if severity == "severe" and patient.get("conservative_care_attempted"):
        boosts["EVID-003"] = (0.25, "Severe disease after failed conservative care; "
                                    "orthopedic evaluation is relevant.")
        boosts["EVID-002"] = (0.25, "Surgery is under discussion; its risks are relevant.")
        boosts["EVID-007"] = (0.20, "Surgery is under discussion; evidence on procedures "
                                    "NOT recommended (arthroscopy) is relevant.")

    # RULE 4 — Patient has had an injection: injection evidence is directly relevant.
    if _has_any(priors, ["injection", "corticosteroid", "steroid"]):
        boosts["EVID-005"] = (0.25, "Patient has had an injection; evidence on injection "
                                    "therapy is directly relevant.")

    # RULE 5 — Overweight/obese: weight loss as a TREATMENT is relevant.
    if _has_any(comorbidities, ["obes", "overweight"]):
        boosts["EVID-008"] = (0.25, "Patient is overweight/obese; weight loss as a "
                                    "treatment option is relevant.")

    # RULE 6 — Conservative care not yet tried: exercise/PT evidence is front-line.
    if not patient.get("conservative_care_attempted", False):
        boosts["EVID-010"] = (0.25, "Structured conservative care not yet tried; exercise "
                                    "therapy is front-line.")
        boosts["EVID-001"] = (0.20, "Conservative management is front-line for this patient.")

    return boosts


def apply_clinical_layer(results, patient, top_k=8, ensure_coverage=True):
    """
    Apply clinical boosts, then guarantee required treatment categories are
    represented in the final selection.
    """
    boosts = clinical_boosts(patient)

    for r in results:
        sid = r["source_id"]
        if sid in boosts:
            boost, why = boosts[sid]
            r["clinical_boost"] = boost
            r["clinical_reason"] = why
            r["score"] = round(r["score"] + boost, 4)
            r["reason"] = r.get("reason", "") + f" | CLINICAL BOOST +{boost}: {why}"
        else:
            r["clinical_boost"] = 0.0
            r["clinical_reason"] = ""

    results.sort(key=lambda r: r["score"], reverse=True)
    selected = list(results[:top_k])

    if not ensure_coverage:
        return selected

    # --- Coverage guarantee ---
    for category in REQUIRED_CATEGORIES:
        selected_ids = {r["source_id"] for r in selected}
        covered = {CARD_CATEGORY.get(r["source_id"]) for r in selected}
        if category in covered:
            continue

        # Best unselected card in the missing category
        candidates = [r for r in results
                      if r["source_id"] not in selected_ids
                      and CARD_CATEGORY.get(r["source_id"]) == category]
        if not candidates:
            continue
        best = candidates[0]

        # Which categories would still be covered if we removed a given card?
        def is_sole_representative(card_result):
            cat = CARD_CATEGORY.get(card_result["source_id"])
            if cat not in REQUIRED_CATEGORIES:
                return False
            same_cat = [r for r in selected
                        if CARD_CATEGORY.get(r["source_id"]) == cat]
            return len(same_cat) <= 1

        # Drop the lowest-scoring card that is NOT the sole holder of a required category
        droppable = [r for r in sorted(selected, key=lambda x: x["score"])
                     if not is_sole_representative(r)]

        if droppable:
            drop = droppable[0]
            selected.remove(drop)
        elif len(selected) >= top_k:
            # Everything is essential; drop the lowest-scoring anyway to make room
            selected.remove(min(selected, key=lambda x: x["score"]))

        best["reason"] = best.get("reason", "") + \
            f" | COVERAGE: added to ensure '{category}' category is represented"
        selected.append(best)

    selected.sort(key=lambda r: r["score"], reverse=True)
    return selected

    # Coverage guarantee: make sure each required category appears at least once.
    selected_ids = {r["source_id"] for r in selected}
    covered = {CARD_CATEGORY.get(r["source_id"]) for r in selected}

    for category in REQUIRED_CATEGORIES:
        if category in covered:
            continue
        # Find the best-scoring unselected card in this missing category
        candidates = [r for r in results
                      if r["source_id"] not in selected_ids
                      and CARD_CATEGORY.get(r["source_id"]) == category]
        if not candidates:
            continue
        best = candidates[0]   # results are already sorted
        # Swap out the lowest-scoring card whose category IS already duplicated
        cat_counts = {}
        for r in selected:
            c = CARD_CATEGORY.get(r["source_id"])
            cat_counts[c] = cat_counts.get(c, 0) + 1
        droppable = [r for r in reversed(selected)
                     if cat_counts.get(CARD_CATEGORY.get(r["source_id"]), 0) > 1]
        if droppable:
            drop = droppable[0]
            selected.remove(drop)
            best["reason"] = best.get("reason", "") + \
                f" | COVERAGE: added to ensure '{category}' category is represented"
            selected.append(best)
            selected_ids.add(best["source_id"])
            covered.add(category)

    selected.sort(key=lambda r: r["score"], reverse=True)
    return selected