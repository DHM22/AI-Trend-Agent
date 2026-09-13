"""
Manual run -- watch a number turn into a recommendation.
========================================================
NOT a test. A hand-driven walk through the full agent chain over a signals
file, printing every intermediate so you can see WHERE each number comes from:

    title
      -> verification confidence + note        (VerificationAgent)
      -> curriculum state: match / searched / why not   (CurriculumAgent)
      -> maturity / relevance / total, each with its input   (EvaluationAgent)
      -> final action tier + action plan       (RecommendationAgent)

This deliberately reproduces the chain inside ``RecommendationAgent.run``
step by step, instead of calling it, so the ``VerifiedTrend``,
``CurriculumMatch`` and ``EvaluationResult`` that ``run`` consumes internally
are held onto and shown. The final tier still comes from the real public
``RecommendationAgent.recommend`` -- no agent is modified or re-implemented.

Modes:
  * With OPENAI_API_KEY set (via .env), the real LLM/tool loop runs.
  * Without it, verification uses its rule-based fallback and the evaluation /
    recommendation prose uses their deterministic templates. Every number below
    is still produced by the real agents; only the wording of the rationale and
    plan changes.

Usage:
    .venv/bin/python 02_src/manual_run.py                       # default file
    .venv/bin/python 02_src/manual_run.py path/to/signals.json
    .venv/bin/python 02_src/manual_run.py signals.json --limit 3
"""

import argparse
import os
import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from clustering import cluster_signals, load_signals
from schemas import CurriculumMatch, EvaluationResult, VerifiedTrend
from agents.verification import VerificationAgent
from agents.curriculum import CurriculumAgent
from agents.evaluation import EvaluationAgent
from agents.recommendation import RecommendationAgent


# ---------------------------------------------------------------------------
# THE CHAIN -- mirrors RecommendationAgent.run, keeping every intermediate.
# ---------------------------------------------------------------------------

class _ChainStep:
    """The intermediates one cluster produces as it moves through the agents."""
    def __init__(self):
        self.trend: VerifiedTrend | None = None
        self.match: CurriculumMatch | None = None
        self.curriculum_checked: bool = False
        self.curriculum_note: str | None = None
        self.evaluation: EvaluationResult | None = None
        self.recommendation = None


def run_chain(cluster, verifier, curriculum, evaluator, recommender) -> _ChainStep:
    """Drive verifier -> curriculum -> evaluator -> recommend, capturing each hop.

    The curriculum seam handles the stub exactly as RecommendationAgent.run
    does: a NotImplementedError means 'never searched' (stay conservative, no
    fault); any other error is an unexpected failure whose cause is recorded.
    """
    step = _ChainStep()

    step.trend = verifier.run(cluster)

    try:
        step.match = curriculum.run(step.trend)
        step.curriculum_checked = True
    except NotImplementedError:
        step.match, step.curriculum_checked = None, False
    except Exception as exc:  # noqa: BLE001 -- mirror run()'s conservative catch
        step.match, step.curriculum_checked = None, False
        step.curriculum_note = f"{type(exc).__name__}: {exc}"

    step.evaluation = evaluator.run(step.trend, step.match)

    step.recommendation = recommender.recommend(
        step.trend, step.match, step.evaluation,
        curriculum_checked=step.curriculum_checked,
        curriculum_note=step.curriculum_note,
    )
    return step


# ---------------------------------------------------------------------------
# EXPLANATIONS -- turn each number back into the input it came from.
# These read only public fields; they describe the agents' documented logic,
# they do not re-decide anything.
# ---------------------------------------------------------------------------

def _maturity_source(confidence: float) -> str:
    return f"confidence {confidence:.2f}"


def _relevance_source(match: CurriculumMatch | None) -> str:
    if match is None:
        return "no curriculum match"
    if match.exact_match is not None:
        return f"exact identifier match on '{match.exact_match}'"
    return f"similarity {match.similarity}"


def _curriculum_state(step: _ChainStep) -> list[str]:
    if step.match is not None:
        m = step.match
        how = (f"exact match on '{m.exact_match}'"
               if m.exact_match is not None else f"similarity {m.similarity}")
        return [f"searched -> matched {m.citation} ({how})"]
    if step.curriculum_checked:
        return ["searched -> no relevant material found"]
    if step.curriculum_note:
        return [f"not searched -- lookup failed unexpectedly ({step.curriculum_note})"]
    return ["not searched -- CurriculumAgent is a stub (NotImplementedError); "
            "tier stays conservative"]


def _tier_inputs(step: _ChainStep) -> str:
    """The exact inputs RecommendationAgent._select_tier keys off."""
    e = step.evaluation
    return (f"maturity={e.maturity_score}, relevance={e.relevance_score}, "
            f"match={'present' if step.match is not None else 'None'}, "
            f"curriculum_checked={step.curriculum_checked}")


# ---------------------------------------------------------------------------
# PRINTING
# ---------------------------------------------------------------------------

def print_step(index: int, step: _ChainStep) -> None:
    trend = step.trend
    ev = step.evaluation
    rec = step.recommendation
    cluster = trend.cluster

    print("\n" + "=" * 78)
    print(f"[{index}] {cluster.representative_title}")
    print(f"    cluster: {len(cluster.signals)} signal(s) from "
          f"{cluster.independent_source_count} independent source(s) "
          f"[tiers: {', '.join(sorted(cluster.source_tiers))}]")

    print("\n  VERIFICATION  (VerificationAgent)")
    print(f"    confidence : {trend.confidence:.2f}")
    print(f"    note       : {trend.verification_note}")

    print("\n  CURRICULUM  (CurriculumAgent)")
    for line in _curriculum_state(step):
        print(f"    {line}")

    print("\n  EVALUATION  (EvaluationAgent)")
    print(f"    maturity   : {ev.maturity_score}/5   <- {_maturity_source(trend.confidence)}")
    print(f"    relevance  : {ev.relevance_score}/5   <- {_relevance_source(step.match)}")
    print(f"    total      : {ev.total_score}/5   <- 0.5*{ev.maturity_score} "
          f"+ 0.5*{ev.relevance_score}")
    if ev.rationale:
        print(f"    rationale  : {ev.rationale}")

    print("\n  RECOMMENDATION  (RecommendationAgent)")
    print(f"    tier       : {rec.recommended_action}")
    print(f"    tier inputs: {_tier_inputs(step)}")
    print(f"    action_plan:")
    for item in rec.action_plan:
        print(f"      - {item}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("signals", nargs="?", default="test_signals_graded.json",
                        help="path to a signals JSON file (default: test_signals_graded.json)")
    parser.add_argument("--limit", type=int, help="only run the first N clusters")
    args = parser.parse_args()

    signals = load_signals(args.signals)
    clusters = cluster_signals(signals)
    if args.limit is not None:
        clusters = clusters[: args.limit]

    have_key = bool(os.environ.get("OPENAI_API_KEY"))
    mode = "LIVE (real LLM + tools)" if have_key else \
        "OFFLINE (rule-based verification + template rationale/plan)"
    print(f"{len(signals)} signal(s) -> {len(clusters)} cluster(s)   |   mode: {mode}")

    # one instance of each agent, reused across clusters
    verifier = VerificationAgent()
    curriculum = CurriculumAgent()
    evaluator = EvaluationAgent()
    recommender = RecommendationAgent()

    for i, cluster in enumerate(clusters, start=1):
        try:
            step = run_chain(cluster, verifier, curriculum, evaluator, recommender)
        except Exception as exc:  # noqa: BLE001 -- a manual tool should not die mid-run
            print("\n" + "=" * 78)
            print(f"[{i}] {cluster.representative_title}")
            print(f"    !! chain failed: {type(exc).__name__}: {exc}")
            continue
        print_step(i, step)

    print("\n" + "=" * 78)
    print("done.")


if __name__ == "__main__":
    main()
