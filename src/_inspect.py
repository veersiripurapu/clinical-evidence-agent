"""Temporary: inspect the pipeline across all patients to inform v2 decisions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import run_pipeline
from evidence_retriever import load_all_cards

SUMMARIES = Path("data") / "evidence" / "summaries"

print("=" * 70)
print("EVIDENCE LIBRARY")
print("=" * 70)
cards = load_all_cards(SUMMARIES)
total_allowed = 0
total_fenced = 0
for c in cards:
    print(f"  [{c.get('source_id')}] {c.get('title')}")
    print(f"      tags: {', '.join(str(t) for t in c.get('tags', []))}")
print(f"\nTotal cards: {len(cards)}")

print("\n" + "=" * 70)
print("PIPELINE BEHAVIOR PER PATIENT")
print("=" * 70)
for pf in sorted((Path("data") / "patients").glob("*.json")):
    r = run_pipeline(pf)
    units = r.get("evidence_units", [])
    claims = sum(len(u.get("allowed_claims", [])) for u in units)
    fences = sum(len(u.get("not_allowed_claims", [])) for u in units)
    comp = r.get("completeness", {})
    print(f"\n{pf.stem}")
    print(f"  status:       {r['status']}")
    print(f"  completeness: {comp.get('present')}/{comp.get('total')} "
          f"({comp.get('score', 0)*100:.0f}%)")
    print(f"  sources used: {len(units)}")
    print(f"  allowed claims available: {claims}")
    print(f"  fences (not-allowed):     {fences}")
    if units:
        print(f"  cards retrieved: {', '.join(u['source_id'] for u in units)}")

print("\n" + "=" * 70)
print("Use this to judge where v2 effort would actually pay off.")
print("=" * 70)