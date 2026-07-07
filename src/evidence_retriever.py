"""
evidence_retriever.py

Pipeline step: given a clinical question AND the patient's context, read every
evidence card on the shelf, score each by how well its tags/topic match, and
return the most relevant cards.

Design notes:
- Transparent keyword/tag matching (no AI, no vector DB) so you can always see
  WHY a card was chosen.
- Retrieval text = clinical question + patient risk/context terms, so the
  librarian pulls evidence relevant to THIS patient, not just the generic topic.
- If nothing matches, it returns a clear "no evidence" signal. In a medical tool,
  no evidence retrieved must mean no medical answer.
- Synonym expansion and body-text matching are intentionally deferred to v2
  (they overlap with a planned semantic-search upgrade).
"""

import re
import json
import frontmatter
from pathlib import Path


def load_all_cards(summaries_dir):
    """Read every .md evidence card in the summaries folder."""
    cards = []
    for path in sorted(Path(summaries_dir).glob("*.md")):
        post = frontmatter.load(path)          # splits the --- block from the body
        card = dict(post.metadata)             # frontmatter fields (source_id, tags, etc.)
        card["summary_text"] = post.content    # the written summary below the ---
        card["file_name"] = path.name
        cards.append(card)
    return cards


def load_patient(file_path):
    """Open a patient JSON file and return it as a Python dictionary."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_patient_context(patient):
    """
    Collect patient-specific risk and context terms so retrieval reflects
    THIS patient, not just the generic clinical question.
    """
    parts = []
    parts.append(str(patient.get("condition", "")))
    parts.append(str(patient.get("condition_severity", "")))
    parts.extend(str(c) for c in patient.get("comorbidities", []))
    parts.extend(str(m) for m in patient.get("current_medications", []))
    for t in patient.get("prior_treatments", []):
        parts.append(str(t.get("treatment", "")))
    parts.extend(str(item) for item in patient.get("missing_or_unclear_information", []))
    return " ".join(parts)


def extract_terms(text):
    """Turn a chunk of text into a clean set of lowercase words for matching."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    stopwords = {
        "the", "and", "for", "with", "what", "are", "this", "that", "from",
        "should", "have", "has", "not", "was", "were", "who", "which", "into",
        "using", "based", "their", "they", "them", "these", "those", "a", "an",
        "of", "to", "in", "on", "or", "is", "be", "by", "as", "at", "it", "its",
        "respect", "benefits", "risks", "evidence", "limitations", "compared",
        "most", "value", "recent", "current", "known", "reported", "unclear",
    }
    return {w for w in words if len(w) > 2 and w not in stopwords}


def gather_card_terms(card):
    """Collect all searchable words for one card, from its tags and topic."""
    parts = []
    parts.append(str(card.get("title", "")))
    parts.append(str(card.get("condition", "")))
    parts.extend(str(t) for t in card.get("tags", []))

    pico = card.get("pico_relevance", {})
    if isinstance(pico, dict):
        parts.append(str(pico.get("population", "")))
        parts.extend(str(i) for i in pico.get("interventions", []))
        parts.extend(str(o) for o in pico.get("outcomes", []))

    return extract_terms(" ".join(parts))


def score_card(question_terms, card):
    """Score one card: how many question/context terms appear in its terms."""
    card_terms = gather_card_terms(card)
    matched = question_terms & card_terms      # the overlap
    return len(matched), sorted(matched)


def retrieve(retrieval_text, summaries_dir, top_k=6):
    """
    Return the top_k most relevant cards for the combined retrieval text
    (clinical question + patient context).

    Returns a tuple: (results, retrieval_terms)
      results: list of dicts, each with source_id, title, score, matched_terms, reason, card
      Empty list means NO evidence matched -> downstream must not fabricate an answer.
    """
    retrieval_terms = extract_terms(retrieval_text)
    cards = load_all_cards(summaries_dir)

    scored = []
    for card in cards:
        score, matched = score_card(retrieval_terms, card)
        if score > 0:
            scored.append({
                "source_id": card.get("source_id"),
                "title": card.get("title"),
                "score": score,
                "matched_terms": matched,
                "reason": f"Matched {score} term(s) in title/tags/PICO: {', '.join(matched)}.",
                "card": card,
            })

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k], retrieval_terms


def main():
    base = Path("data")
    patient_file = base / "patients" / "synthetic_patient_001.json"
    summaries_dir = base / "evidence" / "summaries"

    # The clinical question (as question_builder.py produced it)
    question = (
        "For adults with severe knee osteoarthritis and persistent functional "
        "limitation after conservative therapy, what are the benefits, risks, and "
        "evidence limitations of orthopedic evaluation for surgical management "
        "compared with continued or optimized non-surgical management, with respect "
        "to pain improvement, physical function, adverse events, revision risk?"
    )

    # Combine the question with patient-specific context (fix #1)
    patient = load_patient(patient_file)
    patient_context = build_patient_context(patient)
    retrieval_text = question + " " + patient_context

    results, retrieval_terms = retrieve(retrieval_text, summaries_dir, top_k=6)

    print("=" * 60)
    print(f"EVIDENCE RETRIEVAL FOR: {patient.get('patient_id')}")
    print("=" * 60)
    print("\nRetrieval key terms (question + patient context):")
    print("  " + ", ".join(sorted(retrieval_terms)))

    # Safe-stop behavior (fix #6)
    if not results:
        print("\n" + "!" * 60)
        print("NO MATCHING EVIDENCE CARDS FOUND.")
        print("The agent must NOT generate a treatment comparison.")
        print("Add more evidence cards or revise the clinical question.")
        print("!" * 60)
        return

    print(f"\nTop {len(results)} matching cards:")
    print("-" * 60)
    for rank, r in enumerate(results, start=1):
        print(f"\n  {rank}. [{r['source_id']}] {r['title']}")
        print(f"     Score: {r['score']}")
        print(f"     Reason: {r['reason']}")

    print("\n" + "=" * 60)
    print("NOTE: Retrieval pulls candidate sources for clinician-reviewed evidence.")
    print("=" * 60)


if __name__ == "__main__":
    main()