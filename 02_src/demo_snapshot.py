"""
Demo snapshot -- capture one good run, replay it forever.
==========================================================
The pipeline is non-deterministic in two places, and only one of them is
fixed by the tool cache:

  1. TOOL RESULTS. Cached already (TOOL_CACHE_ONLY=1 in agents/tools.py).
     Same query, same answer.

  2. THE MODEL'S CHOICES. Not cached, and not cacheable. The agent decides
     which queries to run and when to stop. Measured on the same 10 signals
     minutes apart: five of ten trends changed tier. "Organizing Context in a
     Multi-Agent Harness" went from add_new_lesson (no match found) to
     update_existing_material (matched Week 4 slide 17) between runs.

So freezing the tools is not enough. To demo reliably you have to freeze the
OUTPUT, which is what this does.

    # once, when the output looks good:
    python 02_src/demo_snapshot.py --capture --limit 30

    # every time after, including in front of graders:
    python 02_src/demo_snapshot.py --replay

Replay makes ZERO API calls and needs no key or network. It is the same data
your FastAPI endpoint would serve, so the UI can be built against it too.

This is not cheating -- it is the difference between demoing a system and
demoing a coin flip. Say plainly in the presentation that the snapshot is a
recorded run, and that live mode is one flag away.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

DEFAULT_SNAPSHOT = "01_data/demo_snapshot.json"


# ---------------------------------------------------------------------------
# CAPTURE
# ---------------------------------------------------------------------------

def capture(signals_path: str, snapshot_path: str, limit: int,
            offset: int = 0) -> dict:
    from clustering import cluster_signals, load_signals
    from agents.verification import VerificationAgent
    from agents.curriculum import CurriculumAgent
    from agents.evaluation import EvaluationAgent
    from agents.recommendation import RecommendationAgent, collapse_duplicates

    signals = load_signals(signals_path)
    clusters = cluster_signals(signals)
    clusters.sort(key=lambda c: -len(c.signals))
    batch = clusters[offset:offset + limit]

    verifier, curriculum = VerificationAgent(), CurriculumAgent()
    evaluator, recommender = EvaluationAgent(), RecommendationAgent()

    recs = []
    for i, c in enumerate(batch, start=1):
        print(f"  [{i}/{len(batch)}] {c.representative_title[:60]}")
        trend = verifier.run(c)
        checked = trend.confidence >= 0.4
        match = curriculum.run(trend) if checked else None
        ev = evaluator.run(trend, match)
        recs.append(recommender.run(ev, curriculum_checked=checked))

    before = len(recs)
    recs = collapse_duplicates(recs)

    tiers: dict[str, int] = {}
    for r in recs:
        tiers[r.recommended_action] = tiers.get(r.recommended_action, 0) + 1

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_signals": signals_path,
        "signals_in_file": len(signals),
        "clusters_total": len(clusters),
        "clusters_processed": len(batch),
        "duplicates_collapsed": before - len(recs),
        "tier_counts": tiers,
        "recommendations": [r.to_dict() for r in recs],
    }

    out = Path(snapshot_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    return snapshot


# ---------------------------------------------------------------------------
# REPLAY
# ---------------------------------------------------------------------------

def load_snapshot(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"no snapshot at {path} -- run with --capture first")
    return json.loads(p.read_text(encoding="utf-8"))


# order by how much a curriculum lead should care, not alphabetically
TIER_ORDER = ["update_existing_material", "add_new_lesson",
              "add_optional_content", "investigate_larger_change", "watch"]

TIER_LABEL = {
    "update_existing_material": "UPDATE EXISTING MATERIAL",
    "add_new_lesson": "ADD NEW LESSON",
    "add_optional_content": "ADD OPTIONAL CONTENT",
    "investigate_larger_change": "INVESTIGATE LARGER CHANGE",
    "watch": "WATCH",
}


def show(snapshot: dict, actionable_only: bool = False,
         show_evidence: bool = False) -> None:
    recs = snapshot["recommendations"]

    print(f"\ncaptured {snapshot['captured_at'][:16].replace('T', ' ')} UTC")
    print(f"{snapshot['signals_in_file']} signals -> "
          f"{snapshot['clusters_total']} clusters -> "
          f"{snapshot['clusters_processed']} evaluated -> {len(recs)} recommendations")
    if snapshot.get("duplicates_collapsed"):
        print(f"({snapshot['duplicates_collapsed']} duplicate-citation "
              f"recommendation(s) merged)")

    counts = snapshot.get("tier_counts", {})
    summary = "  ".join(f"{TIER_LABEL.get(t, t)}: {counts[t]}"
                        for t in TIER_ORDER if t in counts)
    print(summary)

    by_tier: dict[str, list] = {}
    for r in recs:
        by_tier.setdefault(r["recommended_action"], []).append(r)

    for tier in TIER_ORDER:
        group = by_tier.get(tier)
        if not group:
            continue
        if actionable_only and tier == "watch":
            print(f"\n... {len(group)} watch item(s) hidden (--all to show)")
            continue

        print(f"\n{'=' * 74}\n{TIER_LABEL[tier]}  ({len(group)})\n{'=' * 74}")
        for r in sorted(group, key=lambda x: -(x.get("total_score") or 0)):
            print(f"\n  {r['trend'][:68]}")
            print(f"    score {r.get('total_score')}/5   confidence {r['confidence']}")
            if r.get("match"):
                print(f"    cite  {r['match'].get('citation', '')}")
            for step in r["action_plan"]:
                print(f"      - {step}")
            if show_evidence and r.get("evidence"):
                print("    evidence:")
                for e in r["evidence"][:4]:
                    note = f" -- {e['note'][:70]}" if e.get("note") else ""
                    print(f"      [{e.get('tier', '?')}] {e.get('source', '?')}{note}")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Capture or replay a demo run")
    ap.add_argument("--capture", action="store_true", help="run the pipeline and save")
    ap.add_argument("--replay", action="store_true", help="show a saved run, no API calls")
    ap.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    ap.add_argument("--signals", default="01_data/signals.json")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--all", action="store_true",
                    help="on replay, include watch items (hidden by default)")
    ap.add_argument("--evidence", action="store_true",
                    help="on replay, print the evidence trail for each item")
    args = ap.parse_args()

    if args.capture:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY not set -- capture needs it. "
                             "Replay does not.")

        print(f"capturing {args.limit} cluster(s) from offset {args.offset} ...")
        snap = capture(args.signals, args.snapshot, args.limit, args.offset)
        print(f"\nsaved -> {args.snapshot}")
        print(f"{len(snap['recommendations'])} recommendation(s): "
              + ", ".join(f"{k}={v}" for k, v in snap["tier_counts"].items()))
        print("\nReplay it with:  python 02_src/demo_snapshot.py --replay")
        return

    if args.replay or not args.capture:
        show(load_snapshot(args.snapshot),
             actionable_only=not args.all, show_evidence=args.evidence)


if __name__ == "__main__":
    main()
