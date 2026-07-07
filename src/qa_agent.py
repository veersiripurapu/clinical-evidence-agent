"""
qa_agent.py

Bounded Q&A layer for the Clinical Evidence Agent.

Answers user questions about the selected synthetic patient using ONLY:
- patient context (from the selected patient)
- allowed evidence claims (from the retrieved evidence_units)
- citation labels
- project safety rules

It never generates medical claims from model knowledge. It selects and presents
verified claims. If a question asks for a final decision (diagnosis, prescription,
treatment choice), it reframes honestly and redirects to clinician review.
"""

import re


# Questions that ask the system to DECIDE (which it must never do).
DECISION_PATTERNS = [
    r"\bshould\s+(i|they|the patient|we|he|she)\b",
    r"\bwhat\s+(surgery|treatment|medication|drug)\s+should\b",
    r"\bdo\s+they\s+need\b",
    r"\bdoes\s+(he|she|the patient|this patient)\s+need\b",
    r"\bis\s+surgery\s+(required|needed|necessary)\b",
    r"\bwhich\s+treatment\s+is\s+best\b",
    r"\bwhat\s+is\s+the\s+best\b",
    r"\bcan\s+(they|he|she|the patient)\s+(keep|start|stop|continue|take)\b",
    r"\bprescribe\b",
    r"\bdiagnose\b",
]

# Small topic map: if a question mentions any trigger word, we treat the
# associated topic as relevant. This makes matching smarter than raw word
# overlap (e.g. "sugar" -> diabetes) without any model knowledge.
TOPIC_TRIGGERS = {
    "diabetes": ["diabetes", "diabetic", "a1c", "sugar", "glucose", "glycemic"],
    "obesity": ["obesity", "obese", "weight", "bmi", "overweight"],
    "hypertension": ["hypertension", "blood pressure", "bp"],
    "nsaid": ["nsaid", "nsaids", "ibuprofen", "anti-inflammatory", "painkiller", "medication", "drug", "meds"],
    "injection": ["injection", "corticosteroid", "steroid", "shot"],
    "surgery": ["surgery", "surgical", "arthroplasty", "replacement", "operation", "orthopedic", "tka"],
    "conservative": ["conservative", "exercise", "physical therapy", "pt", "non-surgical", "lifestyle"],
    "risk": ["risk", "risks", "complication", "complications", "infection", "clot", "safety"],
    "missing": ["missing", "unknown", "incomplete", "need to know", "information", "data", "labs"],
}

# Which evidence source_ids relate to each topic (based on your 6 cards).
TOPIC_TO_SOURCES = {
    "diabetes": ["EVID-006"],
    "obesity": ["EVID-006", "EVID-001"],
    "hypertension": ["EVID-006", "EVID-004"],
    "nsaid": ["EVID-004"],
    "injection": ["EVID-005"],
    "surgery": ["EVID-003", "EVID-002"],
    "conservative": ["EVID-001"],
    "risk": ["EVID-002", "EVID-006", "EVID-004"],
    "missing": ["EVID-006"],
}


def is_decision_question(question):
    """True if the question asks the system to make a final medical decision."""
    q = question.lower()
    return any(re.search(p, q) for p in DECISION_PATTERNS)


def detect_topics(question):
    """Return the set of topics a question touches, via the trigger map."""
    q = question.lower()
    topics = set()
    for topic, triggers in TOPIC_TRIGGERS.items():
        if any(trigger in q for trigger in triggers):
            topics.add(topic)
    return topics


def question_words(question):
    """Meaningful lowercase words from the question, for fallback matching."""
    stop = {
        "the", "and", "for", "with", "what", "why", "how", "are", "is", "this",
        "that", "from", "should", "have", "has", "not", "was", "were", "who",
        "which", "into", "using", "based", "their", "they", "them", "these",
        "those", "about", "patient", "does", "can", "will", "would", "could",
    }
    words = re.findall(r"[a-zA-Z]+", question.lower())
    return {w for w in words if len(w) > 2 and w not in stop}


def patient_context_sentence(patient):
    """One clean sentence of patient context."""
    pid = patient.get("patient_id", "the selected synthetic patient")
    age = patient.get("age", "")
    sex = patient.get("sex", "")
    condition = patient.get("condition", "the condition")
    comorbidities = patient.get("comorbidities", [])
    comob = ", ".join(comorbidities) if isinstance(comorbidities, list) and comorbidities else "none documented"
    who = f"{age}-year-old {sex}".strip()
    return (f"For {pid}, the synthetic profile describes a {who} with {condition} "
            f"(comorbidities: {comob}).")


def select_claims(question, evidence_units):
    """
    Choose relevant allowed-claims for the question.
    Priority: topic-matched sources first, then word-overlap fallback.
    Returns a list of {claim, citation, source_id}.
    """
    topics = detect_topics(question)
    wanted_sources = set()
    for t in topics:
        wanted_sources.update(TOPIC_TO_SOURCES.get(t, []))

    qwords = question_words(question)
    selected = []
    seen = set()

    # Pass 1: claims from topic-matched sources
    for unit in evidence_units:
        sid = unit.get("source_id")
        label = unit.get("citation_label") or sid
        if sid in wanted_sources:
            for claim in unit.get("allowed_claims", []):
                if claim not in seen:
                    selected.append({"claim": claim, "citation": label, "source_id": sid})
                    seen.add(claim)

    # Pass 2 (fallback): word-overlap on any claim, if we have too few
    if len(selected) < 2:
        for unit in evidence_units:
            sid = unit.get("source_id")
            label = unit.get("citation_label") or sid
            for claim in unit.get("allowed_claims", []):
                if claim in seen:
                    continue
                claim_words = set(re.findall(r"[a-zA-Z]+", claim.lower()))
                if qwords & claim_words:
                    selected.append({"claim": claim, "citation": label, "source_id": sid})
                    seen.add(claim)

    return selected[:5]  # cap answer length


def answer_question(question, result):
    """
    Answer a question using the pipeline result dict.
    Returns {"status": ..., "answer_markdown": ..., "matched_claims": [...]}.
    """
    question = (question or "").strip()
    if not question:
        return {"status": "empty", "answer_markdown": "_Please type a question above._"}

    patient = result.get("patient", {})
    status = result.get("status", "")

    # Safe-stop consistency: if the pipeline declined, the Q&A declines too.
    if status == "insufficient_patient_data":
        comp = result.get("completeness", {})
        missing = comp.get("missing_fields", [])
        miss = "\n".join(f"- {f}" for f in missing) if missing else "- (not provided)"
        return {"status": status, "answer_markdown": (
            "**This patient record is too incomplete to answer evidence questions.**\n\n"
            "The system declined full review because key information is missing:\n\n"
            f"{miss}\n\n"
            "_Clinician-review note: this prototype does not diagnose, prescribe, or "
            "recommend treatment. A licensed clinician must review the record._")}

    if status == "no_evidence":
        return {"status": status, "answer_markdown": (
            "**No matching evidence was retrieved for this case**, so the system cannot "
            "responsibly answer from the curated evidence library.\n\n"
            "_This prototype does not answer from unsupported model memory._")}

    evidence_units = result.get("evidence_units", [])
    claims = select_claims(question, evidence_units)

    # Graceful, helpful refusal when nothing supported is found.
    if not claims:
        return {"status": "no_supported_answer", "answer_markdown": (
            "I couldn't find a directly supported answer to that in the curated evidence "
            "for this patient. To keep every answer traceable to a source, this system "
            "only answers from its verified evidence cards.\n\n"
            "You could ask about: **conservative management**, **orthopedic/surgical evaluation**, "
            "**surgery risks**, **NSAID safety**, **injection therapy**, or **diabetes/obesity and "
            "surgical risk** — or about this patient's **missing information**.\n\n"
            "_Clinician-review note: this prototype does not diagnose, prescribe, or recommend treatment._")}

    # Build the answer.
    lines = []
    if is_decision_question(question):
        lines.append("**This system can't make a final medical decision or say what the "
                     "patient should do — that's for a clinician.** It can share the "
                     "evidence-supported considerations below.\n")

    lines.append(patient_context_sentence(patient))
    lines.append("\nBased on the curated evidence library:\n")
    for c in claims:
        lines.append(f"- {c['claim']} `[{c['citation']}]`")
    lines.append("\n_Clinician-review note: this answer is for clinician review only. "
                 "It does not diagnose, prescribe, or recommend a final treatment._")

    return {"status": "answered", "answer_markdown": "\n".join(lines), "matched_claims": claims}