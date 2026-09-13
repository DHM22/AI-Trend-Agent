"""
CurriculumAgent -- does this trend touch what we teach?
========================================================
Runs AFTER verification, and only for trends that survived it. Verifying a
rumour against the curriculum is wasted work.

Why this is an agent and not a database call
--------------------------------------------
Similarity search always returns something. Ask it about Kubernetes and it
will hand back your closest slide at a meaningless score. So retrieval alone
cannot answer "is this relevant" -- something has to judge the results.

The agent also chooses ITS OWN queries. Given a release note, it decides
which term is worth searching for: the identifier `AgentExecutor`, not the
prose "agent execution improvements". Measured on our decks, that choice is
the difference between finding the slide and missing it.

And it can search again. If the first query returns nothing useful, it
rephrases -- the same behaviour the VerificationAgent shows when a source is
inconclusive.

Labs vs slides
--------------
The agent is told to check both. A concept slide stays true across versions;
a notebook cell that CALLS a deprecated API stops running. A lab match is a
stronger reason to act, and the returned CurriculumMatch carries `is_lab` so
the recommendation stage can weight it.

Usage:
    python 02_src/agents/curriculum.py --signals 01_data/signals.json --verbose
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from schemas import CurriculumMatch, VerifiedTrend
from agents.tools import TOOL_SCHEMAS, call_tool


MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_STEPS = 4

# only the curriculum tool -- this agent has no business calling GitHub
CURRICULUM_TOOLS = [t for t in TOOL_SCHEMAS
                    if t["function"]["name"] == "search_curriculum"]


SYSTEM_PROMPT = """\
You decide whether a technology trend affects a course curriculum.

You have one tool: search_curriculum. Use it. Do not guess from memory what
the course contains -- you have never seen it.

Choosing a query:
- Search for SPECIFIC technical terms, not prose. If a release note says
  "deprecates AgentExecutor", search "AgentExecutor", not "agent changes".
  Exact identifier matches are far more reliable than topical similarity.
- Search more than once if the first query is unhelpful. Try the library
  name, then the specific class or function, then the concept.
- Check lab notebooks as well as slides (content_type). Lab code that calls a
  changed API actually BREAKS; a slide only goes out of date.

Reading the results:
- Every result has is_reliable. TRUST THAT FIELD, not the similarity number.
  A slide containing the exact term can score 0.30 and still be the right
  answer, while an unrelated slide scores 0.31.
- is_reliable=true means the match is worth considering. It does NOT mean the
  slide is actually about this trend.

THE TEST FOR "AFFECTED"
Ask: if this change shipped tomorrow, would THIS SPECIFIC slide or cell
become wrong, outdated, or broken?

  AFFECTED     a lab cell that calls a method the release renamed
               a slide that documents a parameter the release removed
               a slide teaching a pattern the release deprecated

  NOT AFFECTED a slide that introduces the library in general terms
               a slide that mentions the library while teaching something else
               a lab that imports the library but does not touch what changed

"The course covers LangChain and this is a LangChain release" is NOT enough.
Every LangChain release would match that, and the recommendation would be
useless. Name the specific thing in the slide that this change breaks.

If no retrieved slide meets that test, answer affected: false. Most trends
will NOT affect the curriculum -- that is the normal answer and it is useful.
A false "affected" wastes a curriculum lead's time and is worse than a miss.

Reply with JSON only, no prose and no code fences.

If something is affected:
{"affected": true,
 "citation": "the exact citation string from the result you chose",
 "reason": "one sentence on why this specific slide or cell is affected"}

If nothing is:
{"affected": false,
 "reason": "one sentence on what you searched for and why nothing applies"}
"""


@dataclass
class Step:
    n: int
    query: str
    filters: dict
    result_summary: str

    def __str__(self) -> str:
        f = "".join(f" {k}={v}" for k, v in self.filters.items() if v is not None)
        return f"  [{self.n}] search_curriculum({self.query!r}{f})\n      -> {self.result_summary}"


@dataclass
class CurriculumTrace:
    steps: list[Step] = field(default_factory=list)
    raw_reply: str = ""
    reason: str = ""
    stopped_early: bool = False


def _describe(trend: VerifiedTrend) -> str:
    c = trend.cluster
    lines = [f"TREND: {c.representative_title}",
             f"Verification confidence: {trend.confidence}", "", "SIGNALS:"]
    for s in c.signals:
        lines.append(f"- [{s.source}] {s.title}")
        if s.summary:
            lines.append(f"    {s.summary[:500]}")
    return "\n".join(lines)


def _summarise(result: dict) -> str:
    if "error" in result:
        return f"ERROR: {result['error']}"
    hits = result.get("results", [])
    if not hits:
        return "no results"
    parts = []
    for h in hits[:3]:
        score = h.get("similarity")
        mark = f"exact:{h['exact_match']}" if h.get("exact_match") else f"{score}"
        parts.append(f"{h['citation']} ({mark})")
    return f"{len(hits)} hit(s): " + " | ".join(parts)


class CurriculumAgent:
    """Searches the curriculum and judges whether a trend genuinely affects it."""

    def __init__(self, client=None, model: str = MODEL, max_steps: int = MAX_STEPS):
        self.model = model
        self.max_steps = max_steps
        self._client = client
        self._seen: dict[str, dict] = {}   # citation -> raw hit, for rebuilding the match

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    # -----------------------------------------------------------------
    def run(self, trend: VerifiedTrend,
            trace: CurriculumTrace | None = None) -> CurriculumMatch | None:
        trace = trace if trace is not None else CurriculumTrace()
        self._seen = {}

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _describe(trend)},
        ]

        for step in range(1, self.max_steps + 1):
            try:
                reply = self.client.chat.completions.create(
                    model=self.model, messages=messages,
                    tools=CURRICULUM_TOOLS, tool_choice="auto",
                )
            except Exception as e:
                trace.reason = f"LLM call failed: {e}"
                return None

            msg = reply.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                trace.raw_reply = msg.content or ""
                return self._parse(trace.raw_reply, trace)

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                result = call_tool(tc.function.name, args)

                # remember every hit so we can rebuild the one the agent picks
                for h in result.get("results", []):
                    self._seen[h["citation"]] = h

                trace.steps.append(Step(
                    len(trace.steps) + 1, args.get("question", ""),
                    {"week": args.get("week"), "type": args.get("content_type")},
                    _summarise(result)))

                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result)[:4000]})

        trace.stopped_early = True
        messages.append({"role": "user",
                         "content": "Stop searching. Give your JSON verdict now."})
        try:
            reply = self.client.chat.completions.create(model=self.model, messages=messages)
            trace.raw_reply = reply.choices[0].message.content or ""
            return self._parse(trace.raw_reply, trace)
        except Exception as e:
            trace.reason = f"LLM call failed after {self.max_steps} steps: {e}"
            return None

    # -----------------------------------------------------------------
    def _parse(self, text: str, trace: CurriculumTrace) -> CurriculumMatch | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            trace.reason = "model did not return valid JSON"
            return None

        trace.reason = str(data.get("reason", "")).strip()

        if not data.get("affected"):
            return None

        citation = str(data.get("citation", "")).strip()
        hit = self._seen.get(citation)

        if hit is None:
            # the model cited something it never retrieved -- a hallucinated
            # citation is worse than no match, so refuse it
            trace.reason = (f"model claimed a match on '{citation}' but that "
                            f"citation was never returned by a search. Discarded.")
            return None

        return CurriculumMatch(
            week=hit.get("week"),
            topic=hit.get("topic", ""),
            source_file=hit.get("source_file", ""),
            slide_number=hit.get("slide_number", 0),
            matched_text=hit.get("text", "")[:400],
            similarity=hit.get("similarity"),
            exact_match=hit.get("exact_match"),
            content_type=hit.get("content_type", "slides"),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    from clustering import cluster_signals, load_signals
    from agents.verification import VerificationAgent

    ap = argparse.ArgumentParser(description="Match verified trends to the curriculum")
    ap.add_argument("--signals", default="01_data/signals.json")
    ap.add_argument("--index", type=int, help="only cluster N")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--verbose", action="store_true", help="show the search trace")
    ap.add_argument("--skip-verify", action="store_true",
                    help="skip verification, match every cluster (cheaper while testing)")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set -- this agent needs it.")
        return

    clusters = cluster_signals(load_signals(args.signals))
    clusters.sort(key=lambda c: -len(c.signals))
    chosen = [clusters[args.index]] if args.index is not None else clusters[:args.limit]

    verifier = VerificationAgent()
    agent = CurriculumAgent()

    for c in chosen:
        print(f"\n{'='*72}\n{c.representative_title[:70]}")

        if args.skip_verify:
            from schemas import VerifiedTrend
            trend = VerifiedTrend(cluster=c, confidence=1.0,
                                   verification_note="skipped", evidence=[])
        else:
            trend = verifier.run(c)
            print(f"  verified: {trend.confidence}")
            if trend.confidence < 0.4:
                print("  -> too low to be worth checking against the curriculum")
                continue

        trace = CurriculumTrace()
        match = agent.run(trend, trace)

        if args.verbose and trace.steps:
            print("\n  searches the agent chose:")
            for s in trace.steps:
                print(s)

        print()
        if match:
            kind = "LAB" if match.is_lab else "slides"
            print(f"  AFFECTED [{kind}]: {match.citation}")
            print(f"  reason  : {trace.reason}")
            print(f"  evidence: {match.matched_text[:150]}")
        else:
            print(f"  not affected: {trace.reason}")


if __name__ == "__main__":
    main()
