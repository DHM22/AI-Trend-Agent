"""
EvaluationAgent tests -- coverage-reading scoring + rationale behaviour.
========================================================================
Everything here runs with NO API key and NO network. Scores are pure functions
of the inputs, so they are asserted exactly; the rationale is exercised through
an injected fake client (and, with no client, through the deterministic
template), so no test ever calls OpenAI.

Run:
    .venv/bin/python 02_src/tests/test_evaluation.py
    # or, if pytest is installed:
    .venv/bin/pytest 02_src/tests/test_evaluation.py
"""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import (
    RawSignal, TrendCluster, VerifiedTrend, CurriculumMatch,
    RELEVANCE_FLOOR,
)
from agents.evaluation import (
    EvaluationAgent, _maturity_score, _relevance_score, _total_score,
)


# --- fakes & builders ------------------------------------------------------

class FakeLLM:
    """One chat completion, no tools. Optionally raises to test the fallback."""
    def __init__(self, content="model rationale text", raises=False):
        self._content, self._raises = content, raises
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        if self._raises:
            raise RuntimeError("simulated API failure")
        msg = type("M", (), {"content": self._content})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def trend(confidence: float, note: str = "checked the claim") -> VerifiedTrend:
    c = TrendCluster("Some AI development",
                     [RawSignal("Some AI development", "github", "primary", "")])
    return VerifiedTrend(cluster=c, confidence=confidence, verification_note=note)


def match(similarity=None, exact=None, week=2, topic="RAG Introduction",
          slide=5, text="a slide about the topic") -> CurriculumMatch:
    return CurriculumMatch(week=week, topic=topic, source_file="RAG.pdf",
                           slide_number=slide, matched_text=text,
                           similarity=similarity, exact_match=exact)


# ===========================================================================
# MATURITY -- confidence (0.0-1.0) -> 1-5, bands mirror verification
# ===========================================================================

def test_maturity_bands():
    assert _maturity_score(0.95) == 5
    assert _maturity_score(0.85) == 5      # lower edge of top band
    assert _maturity_score(0.84) == 4
    assert _maturity_score(0.70) == 4
    assert _maturity_score(0.69) == 3
    assert _maturity_score(0.50) == 3
    assert _maturity_score(0.30) == 2
    assert _maturity_score(0.29) == 1
    assert _maturity_score(0.0) == 1


# ===========================================================================
# RELEVANCE -- COVERAGE reading: stronger match -> higher score
# ===========================================================================

def test_relevance_no_match_scores_lowest():
    assert _relevance_score(None) == 1


def test_relevance_exact_match_scores_top_regardless_of_similarity():
    # a literal identifier hit is trustworthy even at a low embedding distance
    assert _relevance_score(match(similarity=0.30, exact="FAISS")) == 5
    assert _relevance_score(match(similarity=None, exact="LangChain")) == 5


def test_relevance_similarity_bands():
    assert _relevance_score(match(similarity=0.66)) == 5
    assert _relevance_score(match(similarity=0.65)) == 5
    assert _relevance_score(match(similarity=0.55)) == 4
    assert _relevance_score(match(similarity=RELEVANCE_FLOOR)) == 3   # 0.48
    assert _relevance_score(match(similarity=0.47)) == 2             # below floor
    assert _relevance_score(match(similarity=0.0)) == 2


# ===========================================================================
# TOTAL -- 50/50 blend on the same 1-5 scale
# ===========================================================================

def test_total_is_even_blend():
    assert _total_score(5, 3) == 4.0
    assert _total_score(4, 1) == 2.5
    assert _total_score(1, 1) == 1.0
    assert _total_score(5, 5) == 5.0


def test_total_matches_run_output():
    result = EvaluationAgent().run(trend(0.90), match(similarity=0.60))
    assert (result.maturity_score, result.relevance_score) == (5, 4)
    assert result.total_score == _total_score(5, 4) == 4.5


# ===========================================================================
# COVERAGE READING -- the design decision, asserted directly
# ===========================================================================

def test_coverage_reading_gap_stays_low_but_is_flagged_in_prose():
    """A real trend with no coverage keeps relevance 1 (coverage reading), but
    the rationale flags it as a possible gap -- the number is not inverted."""
    result = EvaluationAgent().run(trend(0.95), None)   # no client -> template
    assert result.relevance_score == 1
    assert result.maturity_score == 5
    assert result.total_score == 3.0
    assert "gap" in result.rationale.lower()


def test_low_maturity_gap_is_not_talked_up():
    """An unverified trend with no coverage should not be pitched as a lesson."""
    result = EvaluationAgent().run(trend(0.20), None)
    assert (result.maturity_score, result.relevance_score) == (1, 1)
    assert "gap" not in result.rationale.lower()


# ===========================================================================
# RATIONALE -- model-written when available, template fallback otherwise
# ===========================================================================

def test_rationale_uses_injected_model_reply():
    agent = EvaluationAgent(client=FakeLLM(content="This trend is well established."))
    result = agent.run(trend(0.90), match(similarity=0.70))
    assert result.rationale == "This trend is well established."


def test_rationale_falls_back_to_template_on_api_failure():
    agent = EvaluationAgent(client=FakeLLM(raises=True))
    result = agent.run(trend(0.90), match(similarity=0.70))
    # the deterministic template describes the same score, never empty
    assert result.rationale
    assert "Overall" in result.rationale and "Relevance 5/5" in result.rationale


def test_rationale_falls_back_when_model_returns_empty():
    agent = EvaluationAgent(client=FakeLLM(content="   "))
    result = agent.run(trend(0.60), match(similarity=0.50))
    assert result.rationale.startswith("Overall")


def test_template_never_empty_and_cites_the_slide():
    result = EvaluationAgent().run(trend(0.72), match(similarity=0.58))
    assert result.rationale
    assert match(similarity=0.58).citation in result.rationale


def test_result_carries_inputs_through():
    t, m = trend(0.80), match(similarity=0.60)
    result = EvaluationAgent().run(t, m)
    assert result.trend is t and result.match is m


# ===========================================================================
# RUNNER (pytest picks up the test_* functions above directly)
# ===========================================================================

def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failures = 0
    print("== EvaluationAgent ==")
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
