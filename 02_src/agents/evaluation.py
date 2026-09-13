"""
EvaluationAgent -- how much should we care about this verified trend?
=====================================================================
Third agent in the chain. Consumes a ``VerifiedTrend`` (is it real?) and an
optional ``CurriculumMatch`` (does it touch what we teach?) and returns an
``EvaluationResult``: two 1-5 scores, a blended total, and a written rationale.

Division of labour -- DETERMINISTIC SCORE, MODEL-WRITTEN RATIONALE:

  * Python computes the scores. Both inputs are already numbers we trust --
    verification confidence (0.0-1.0) and curriculum similarity -- so the score
    is a pure, banded mapping of those, not something a model is asked to
    invent. The number is therefore reproducible, testable with no API key, and
    cannot be talked upward by a persuasive rationale.

  * The model writes the rationale. It is TOLD the scores and asked to explain
    them in plain language -- never asked to produce or revise a number. If the
    call fails or no key is set, a deterministic template built from the same
    facts is used instead, so the rationale can never contradict the score.

Maturity -- "is this real?", mapped from VerificationAgent confidence. The
bands mirror the verification confidence guide so the two agents stay aligned:

    >= 0.85  ->  5   (primary source, corroborated)
    >= 0.70  ->  4   (primary source, uncorroborated)
    >= 0.50  ->  3
    >= 0.30  ->  2
    <  0.30  ->  1   (single unverified source, or does not appear to exist)

Relevance -- COVERAGE reading. "How strongly does this connect to material we
already teach?" A strong curriculum match scores high; no match scores low.

    exact identifier match       ->  5   (the slide literally names it)
    similarity >= 0.65           ->  5
    similarity >= 0.55           ->  4
    similarity >= RELEVANCE_FLOOR->  3
    match present but below floor->  2
    no match at all              ->  1

We deliberately do NOT invert this for gaps: a verified trend with no coverage
is arguably the most valuable signal (a candidate new lesson), but folding that
into the relevance NUMBER would make the 50/50 blend mean two contradictory
things. The gap case is surfaced in the RATIONALE instead, and acted on by the
RecommendationAgent's action tier.

Total = 0.5 * maturity + 0.5 * relevance, on the same 1-5 scale.

Usage:
    from agents.evaluation import EvaluationAgent
    result = EvaluationAgent().run(trend, match)

    # offline / testing: inject a fake client, or pass none to use the template
    EvaluationAgent(client=fake).run(trend, match)
"""

import os
import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from schemas import (
    CurriculumMatch,
    EvaluationResult,
    VerifiedTrend,
    MATURITY_WEIGHT,
    RELEVANCE_WEIGHT,
    RELEVANCE_FLOOR,
)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# ---------------------------------------------------------------------------
# SCORING -- pure functions, no API key, straightforward to test
# ---------------------------------------------------------------------------

def _maturity_score(confidence: float) -> int:
    """Verification confidence (0.0-1.0) -> 1-5. Bands mirror the verification
    confidence guide so 'mature' here means the same thing it does there."""
    if confidence >= 0.85:
        return 5
    if confidence >= 0.70:
        return 4
    if confidence >= 0.50:
        return 3
    if confidence >= 0.30:
        return 2
    return 1


def _relevance_score(match: CurriculumMatch | None) -> int:
    """CurriculumMatch -> 1-5, COVERAGE reading: stronger match, higher score.

    Gates on the match being reliable, never on raw similarity -- an exact
    identifier hit is trustworthy even at a low embedding distance (a slide
    literally containing 'FAISS' measured 0.303), so it scores top regardless.
    """
    if match is None:
        return 1
    if match.exact_match is not None:
        return 5
    similarity = match.similarity or 0.0
    if similarity >= 0.65:
        return 5
    if similarity >= 0.55:
        return 4
    if similarity >= RELEVANCE_FLOOR:
        return 3
    return 2                      # a match object exists but is too weak to trust


def _total_score(maturity: int, relevance: int) -> float:
    """The 50/50 blend, on the same 1-5 scale as its parts."""
    return round(MATURITY_WEIGHT * maturity + RELEVANCE_WEIGHT * relevance, 2)


# ---------------------------------------------------------------------------
# RATIONALE
# ---------------------------------------------------------------------------

RATIONALE_SYSTEM = """\
You explain evaluation scores for an AI-curriculum trend monitor. A trend has
ALREADY been scored on two axes, each 1-5:

- maturity  = how real / established the development is (from a verification step)
- relevance = how strongly it connects to material the course already teaches

You are given the scores and the facts they were computed from. Write TWO or
THREE sentences explaining WHY those scores are what they are, in plain language
a curriculum lead can act on. Cover: how solid the evidence is, and whether the
matched material is REINFORCED, made OUTDATED, or simply ABSENT (a gap).

Rules:
- Do NOT output any score, number, or verdict of your own, and do not dispute
  the scores you were given. Your job is to explain them, not to re-decide them.
- No preamble, no bullet points, no headings. Just the sentences.
"""


class EvaluationAgent:
    """Score the maturity and relevance of a verified trend, and explain it."""

    def __init__(self, client=None, model: str = MODEL):
        self._client = client      # injectable, so tests can pass a fake
        self.model = model

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI       # imported late: no key needed to import this module
            self._client = OpenAI()
        return self._client

    # -- public API --------------------------------------------------------

    def run(
        self,
        trend: VerifiedTrend,
        match: CurriculumMatch | None,
    ) -> EvaluationResult:
        """Evaluate a trend and explain the resulting scores."""
        maturity = _maturity_score(trend.confidence)
        relevance = _relevance_score(match)
        total = _total_score(maturity, relevance)
        rationale = self._rationale(trend, match, maturity, relevance, total)

        return EvaluationResult(
            trend=trend,
            match=match,
            maturity_score=maturity,
            relevance_score=relevance,
            total_score=total,
            rationale=rationale,
        )

    # -- rationale: model-written, with a deterministic fallback -----------

    def _rationale(self, trend: VerifiedTrend, match: CurriculumMatch | None,
                   maturity: int, relevance: int, total: float) -> str:
        template = self._template(trend, match, maturity, relevance, total)

        # no key and no injected client -> the template is the rationale
        if self._client is None and not os.environ.get("OPENAI_API_KEY"):
            return template

        try:
            reply = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": RATIONALE_SYSTEM},
                    {"role": "user", "content": self._prompt(
                        trend, match, maturity, relevance, total)},
                ],
            )
            text = (reply.choices[0].message.content or "").strip()
            # an empty reply is no better than no call -- keep the template
            return text or template
        except Exception:
            # a missing key, an import error, or an API failure must never sink
            # the pipeline: the deterministic rationale still describes the score
            return template

    def _prompt(self, trend: VerifiedTrend, match: CurriculumMatch | None,
                maturity: int, relevance: int, total: float) -> str:
        cluster = trend.cluster
        lines = [
            f"TREND: {cluster.representative_title}",
            f"Verification confidence: {trend.confidence:.2f}",
            f"Verification note: {trend.verification_note}",
            "",
            f"Maturity score: {maturity}/5",
            f"Relevance score: {relevance}/5",
            f"Total score: {total}/5",
            "",
        ]
        if match is None:
            lines.append("Curriculum match: NONE -- no slide in the current "
                         "material relates to this trend.")
        else:
            how = (f"literal match on '{match.exact_match}'"
                   if match.exact_match is not None
                   else f"similarity {match.similarity}")
            lines.append(f"Curriculum match: {match.citation} ({how})")
            lines.append(f"Matched slide text: {match.matched_text[:400]}")
        return "\n".join(lines)

    def _template(self, trend: VerifiedTrend, match: CurriculumMatch | None,
                  maturity: int, relevance: int, total: float) -> str:
        """Built FROM the facts, so it can never describe a different score."""
        mat = (f"Maturity {maturity}/5: verification confidence "
               f"{trend.confidence:.2f}")

        if match is None:
            rel = "Relevance 1/5: no current curriculum material matches this trend"
            # coverage reading keeps the number low; the gap is called out in prose
            gap = (" A verified development with no existing coverage may be a "
                   "curriculum gap worth a new lesson." if maturity >= 4 else "")
        else:
            how = (f"exact match on '{match.exact_match}'"
                   if match.exact_match is not None
                   else f"similarity {match.similarity}")
            rel = (f"Relevance {relevance}/5: matches {match.citation} ({how}), "
                   f"so this touches material we already teach")
            gap = ""

        return f"Overall {total}/5. {mat}. {rel}.{gap}"


# ---------------------------------------------------------------------------
# CLI -- evaluate the verified clusters from a saved signals file
# ---------------------------------------------------------------------------

def main():
    import argparse

    from clustering import cluster_signals, load_signals
    from agents.verification import VerificationAgent
    from agents.curriculum import CurriculumAgent

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description="Evaluate verified trend clusters")
    ap.add_argument("--signals", default="01_data/signals.json")
    ap.add_argument("--limit", type=int, default=5, help="how many clusters")
    args = ap.parse_args()

    clusters = cluster_signals(load_signals(args.signals))
    verifier = VerificationAgent()
    curriculum = CurriculumAgent()
    evaluator = EvaluationAgent()

    for c in clusters[:args.limit]:
        trend = verifier.run(c)
        try:
            match = curriculum.run(trend)     # still a stub -> falls through to None
        except Exception:
            match = None
        result = evaluator.run(trend, match)

        print(f"\n{'=' * 70}\n{c.representative_title[:68]}")
        print(f"  maturity  : {result.maturity_score}/5  "
              f"(confidence {trend.confidence:.2f})")
        print(f"  relevance : {result.relevance_score}/5  "
              f"({match.citation if match else 'no curriculum match'})")
        print(f"  total     : {result.total_score}/5")
        print(f"  rationale : {result.rationale}")


if __name__ == "__main__":
    main()
