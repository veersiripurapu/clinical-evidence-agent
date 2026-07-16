"""
semantic_retriever.py

Hybrid retrieval: transparent keyword matching + FACETED semantic similarity.

Why faceted?
A single blob query ("everything about this patient") produces an undiscriminating
embedding — every knee-OA card scores ~0.5-0.7 and nothing stands out. Instead we
generate several TARGETED sub-queries from the patient's actual situation
(medications, comorbidities, treatment history, severity) and score each card
against every facet, keeping its BEST match. A card that answers one narrow
question sharply is no longer drowned out by three topics it doesn't address.

Degrades gracefully to keyword-only if the embedding model is unavailable.
"""

import re
from pathlib import Path

from evidence_retriever import (
    load_all_cards,
    extract_terms,
    gather_card_terms,
    build_patient_context,
    load_patient,
)

_MODEL = None
_MODEL_FAILED = False
MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    global _MODEL, _MODEL_FAILED
    if _MODEL is not None:
        return _MODEL
    if _MODEL_FAILED:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL_NAME)
        return _MODEL
    except Exception as exc:
        print(f"[semantic_retriever] Model unavailable ({exc}); keyword-only.")
        _MODEL_FAILED = True
        return None


def build_query_facets(patient, clinical_question=None):
    """
    Generate several TARGETED queries from the patient record.
    Each facet is a narrow clinical question a clinician might actually ask.
    """
    facets = []

    condition = patient.get("condition", "knee osteoarthritis")
    severity = patient.get("condition_severity", "")
    comorbidities = [str(c) for c in patient.get("comorbidities", [])]
    meds = [str(m) for m in patient.get("current_medications", [])]
    priors = [str(t.get("treatment", "")) for t in patient.get("prior_treatments", [])]
    missing = [str(m) for m in patient.get("missing_or_unclear_information", [])]

    # Facet 1: the core condition + severity
    facets.append(f"treatment options for {severity} {condition}".strip())

    # Facet 2: medication safety (this is the facet that should surface topical NSAIDs)
    if meds:
        med_str = ", ".join(meds)
        comorb_str = ", ".join(comorbidities) if comorbidities else "no comorbidities"
        facets.append(
            f"pain medication safety and safer alternatives for a patient taking "
            f"{med_str} with {comorb_str}"
        )

    # Facet 3: surgical risk given comorbidities
    if comorbidities:
        facets.append(
            f"surgical risk and preoperative optimization for a patient with "
            f"{', '.join(comorbidities)}"
        )

    # Facet 4: what to do after prior treatments
    if priors:
        facets.append(
            f"next treatment options after {', '.join(priors)} for {condition}"
        )

    # Facet 5: conservative (non-surgical) management
    facets.append(f"non-surgical conservative management of {condition}")

    # Facet 6: surgical options
    facets.append(f"surgical options and their risks for {condition}")

    # Facet 7: missing information / what to assess
    if missing:
        facets.append(f"assessments needed before treatment decisions: {', '.join(missing[:4])}")

    return [f for f in facets if f.strip()]


def card_text_for_embedding(card):
    parts = [
        str(card.get("title", "")),
        " ".join(str(t) for t in card.get("tags", [])),
        str(card.get("summary_text", ""))[:1200],
    ]
    return " ".join(parts)


def cosine_matrix(query_vecs, card_vecs):
    """Return a matrix of cosine similarities [n_queries x n_cards]."""
    import numpy as np
    q = np.asarray(query_vecs, dtype=float)
    c = np.asarray(card_vecs, dtype=float)
    q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-9)
    c = c / (np.linalg.norm(c, axis=1, keepdims=True) + 1e-9)
    return q @ c.T


def retrieve_faceted(patient, summaries_dir, clinical_question=None, top_k=8,
                     keyword_weight=0.35, semantic_weight=0.65):
    """
    Score cards by keyword overlap + BEST semantic match across query facets.
    Semantic is weighted higher now, because faceted queries give it real spread.
    """
    cards = load_all_cards(summaries_dir)
    facets = build_query_facets(patient, clinical_question)

    # Keyword side (unchanged, transparent)
    keyword_query = (clinical_question or "") + " " + build_patient_context(patient)
    query_terms = extract_terms(keyword_query)
    keyword_raw = []
    matched_per_card = []
    for card in cards:
        matched = sorted(query_terms & gather_card_terms(card))
        matched_per_card.append(matched)
        keyword_raw.append(len(matched))
    max_kw = max(keyword_raw) if keyword_raw else 0

    # Semantic side (faceted)
    model = _get_model()
    semantic_best = [0.0] * len(cards)
    best_facet = [""] * len(cards)
    semantic_available = model is not None

    if semantic_available:
        try:
            card_vecs = model.encode([card_text_for_embedding(c) for c in cards])
            facet_vecs = model.encode(facets)
            sims = cosine_matrix(facet_vecs, card_vecs)   # [n_facets x n_cards]
            for j in range(len(cards)):
                col = sims[:, j]
                i_best = int(col.argmax())
                semantic_best[j] = float(col[i_best])
                best_facet[j] = facets[i_best]
        except Exception as exc:
            print(f"[semantic_retriever] Embedding failed ({exc}); keyword-only.")
            semantic_available = False

    # Normalize semantic scores across cards so they have spread
    if semantic_available and semantic_best:
        lo, hi = min(semantic_best), max(semantic_best)
        rng = (hi - lo) or 1.0
        semantic_norm = [(s - lo) / rng for s in semantic_best]
    else:
        semantic_norm = [0.0] * len(cards)

    results = []
    for i, card in enumerate(cards):
        kw_norm = (keyword_raw[i] / max_kw) if max_kw else 0.0
        sem = semantic_norm[i]

        if semantic_available:
            score = keyword_weight * kw_norm + semantic_weight * sem
            reason = (f"keywords ({keyword_raw[i]}: {', '.join(matched_per_card[i][:5])})"
                      f" + best semantic facet \"{best_facet[i][:60]}...\" "
                      f"({semantic_best[i]:.2f})")
        else:
            score = kw_norm
            reason = (f"keywords ({keyword_raw[i]}: {', '.join(matched_per_card[i][:5])})"
                      f" [semantic unavailable]")

        results.append({
            "source_id": card.get("source_id"),
            "title": card.get("title"),
            "keyword_score": keyword_raw[i],
            "semantic_raw": round(semantic_best[i], 3),
            "semantic_norm": round(sem, 3),
            "best_facet": best_facet[i],
            "score": round(score, 4),
            "matched_terms": matched_per_card[i],
            "reason": reason,
            "card": card,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    results = [r for r in results if r["keyword_score"] > 0 or r["semantic_raw"] >= 0.2]

    # Apply the clinical-relevance layer (boosts + category coverage)
    from clinical_relevance import apply_clinical_layer
    final = apply_clinical_layer(results, patient, top_k=top_k, ensure_coverage=True)

    return final, query_terms


def main():
    from evidence_retriever import retrieve as retrieve_keyword
    from question_builder import build_pico

    base = Path("data")
    summaries = base / "evidence" / "summaries"

    for pf in sorted((base / "patients").glob("*.json")):
        patient = load_patient(pf)
        try:
            pico = build_pico(patient)
            question = pico["clinical_question"]
        except Exception:
            question = ""

        kw_query = question + " " + build_patient_context(patient)
        kw_results, _ = retrieve_keyword(kw_query, summaries, top_k=6)
        fa_results, _ = retrieve_faceted(patient, summaries, question, top_k=8)

        kw_ids = [r["source_id"] for r in kw_results]
        fa_ids = [r["source_id"] for r in fa_results]

        print("=" * 74)
        print(patient["patient_id"])
        print("=" * 74)
        print(f"  KEYWORD-ONLY: {', '.join(kw_ids)}")
        print(f"  FACETED:      {', '.join(fa_ids)}")
        gained = [i for i in fa_ids if i not in kw_ids]
        lost = [i for i in kw_ids if i not in fa_ids]
        if gained:
            print(f"  >> GAINED: {', '.join(gained)}")
        if lost:
            print(f"  >> dropped: {', '.join(lost)}")
        print("\n  Detail:")
        for r in fa_results:
            print(f"    [{r['source_id']}] score={r['score']:.3f} "
                  f"(kw={r['keyword_score']}, sem_raw={r['semantic_raw']:.2f}, "
                  f"sem_norm={r['semantic_norm']:.2f})")
            print(f"        best facet: {r['best_facet'][:70]}")
        print()


if __name__ == "__main__":
    main()