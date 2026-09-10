"""
VerificationAgent -- the agentic core.
=======================================
Decides whether a trend's claims are real, and decides FOR ITSELF when it has
looked hard enough.

This is the piece that makes the project agentic rather than a script. The
old version was:

    if has_primary and n_sources >= 2: confidence = 0.9

A fixed formula. Same inputs, same output, no judgement. It could not react
to a claim that looked suspicious, and it could not go looking for more.

This version runs a ReAct loop:

    Thought      -- "a single tweet claims a 10x speedup, that needs checking"
    Action       -- github_lookup("RapidAgent")
    Observation  -- no such repository
    Thought      -- "still not confident, try the exact phrasing"
    Action       -- github_lookup("RapidAgent framework tool calling")
    Observation  -- still nothing
    Final        -- confidence 0.15, "no primary source exists for this claim"

We do not write that sequence. The model chooses each step from what it has
seen so far, and it can make a second call the first version would never have
made. Every step is recorded in `trace`, which is what the UI shows as the
evidence trail and what makes the decision auditable.

Setup:
    pip install openai python-dotenv
    OPENAI_API_KEY=sk-... in .env at the repo root

Usage:
    python 02_src/agents/verification.py --signals 01_data/signals.json
    python 02_src/agents/verification.py --signals 01_data/signals.json --index 0 --verbose
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import Evidence, TrendCluster, VerifiedTrend
from agents.tools import TOOL_SCHEMAS, call_tool


MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# How many tool calls the agent may make before we force it to answer.
# Not a target -- most trends resolve in one or two. This is a stop so a
# confused model cannot loop forever and burn the API budget.
MAX_STEPS = 5


SYSTEM_PROMPT = """\
You verify technology claims for a curriculum team. Your only question is:
IS THIS REAL? Do not consider whether it is relevant to any course -- a
different agent decides that. Judging relevance here would bias verification,
so ignore it entirely.

You have tools. Use them when the signals alone are not enough to judge. You
decide how many times to call them; call again if a result was inconclusive
and a different query might help. Stop as soon as you can justify a number.

How to weigh sources:
- primary   = the project's own words: a GitHub release, an official blog, the
              paper itself. Strong evidence.
- secondary = someone reporting on it: news article, forum post, tweet. Weak
              on its own.
- Independent sources matter more than repeated ones. Three articles quoting
  one press release is still one source.

Confidence guide:
  0.85 - 1.0   confirmed by a primary source AND corroborated independently
  0.7  - 0.85  confirmed by a primary source, not yet corroborated
  0.4  - 0.7   several secondary sources agree, no primary source found
  0.0  - 0.4   single unverified source, or the thing does not appear to exist

Be willing to return a LOW number. An honest 0.2 is more useful to us than a
confident guess. If a tool returns no results, that is evidence -- a project
that does not exist on GitHub is unlikely to be a real trend.

When you are done, reply with JSON only, no prose and no code fences:
{"confidence": 0.0-1.0,
 "note": "one or two sentences on what you checked and what convinced you",
 "evidence": [{"source": "where", "tier": "primary|secondary", "note": "what it showed"}]}
"""


@dataclass
class Step:
    """One Thought/Action/Observation cycle, for the audit trail."""
    n: int
    tool: str
    arguments: dict
    result_summary: str

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"  [{self.n}] {self.tool}({args})\n      -> {self.result_summary}"


@dataclass
class VerificationTrace:
    steps: list[Step] = field(default_factory=list)
    raw_reply: str = ""
    stopped_early: bool = False   # hit MAX_STEPS instead of finishing


def _describe_cluster(cluster: TrendCluster) -> str:
    """What the model sees. Include tiers -- they are half the reasoning."""
    lines = [f"TREND: {cluster.representative_title}", "", "SIGNALS:"]
    for s in cluster.signals:
        lines.append(f"- [{s.source} / {s.source_tier}] {s.title}")
        if s.summary:
            lines.append(f"    {s.summary[:400]}")
    lines.append("")
    lines.append(f"{len(cluster.signals)} signal(s) from "
                 f"{cluster.independent_source_count} independent source(s): "
                 f"{', '.join(sorted(cluster.source_tiers))}")
    return "\n".join(lines)


def _summarise_result(result: dict) -> str:
    """Short human-readable form of a tool result, for the trace."""
    if "error" in result:
        return f"ERROR: {result['error']}"
    if "results" in result:
        n = result.get("found", 0)
        if n == 0:
            return "no results" + (f" ({result['note']})" if "note" in result else "")
        first = result["results"][0]
        label = first.get("full_name") or first.get("citation") or ""
        extra = f", {first['stars']} stars" if "stars" in first else ""
        return f"{n} result(s), top: {label}{extra}"
    return json.dumps(result)[:160]


class VerificationAgent:
    """Runs a ReAct loop to decide whether a trend's claims hold up."""

    def __init__(self, client=None, model: str = MODEL, max_steps: int = MAX_STEPS):
        self.model = model
        self.max_steps = max_steps
        self._client = client      # injectable, so tests can pass a fake

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI          # imported late: no key needed to import this module
            self._client = OpenAI()
        return self._client

    # -----------------------------------------------------------------
    def run(self, cluster: TrendCluster,
            trace: VerificationTrace | None = None) -> VerifiedTrend:
        trace = trace if trace is not None else VerificationTrace()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _describe_cluster(cluster)},
        ]

        for step in range(1, self.max_steps + 1):
            try:
                reply = self.client.chat.completions.create(
                    model=self.model, messages=messages,
                    tools=TOOL_SCHEMAS, tool_choice="auto",
                )
            except Exception as e:
                # never let an API failure kill the pipeline -- fall back to
                # what the signals alone tell us
                return self._fallback(cluster, f"LLM call failed: {e}", trace)

            msg = reply.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                trace.raw_reply = msg.content or ""
                return self._parse(cluster, trace.raw_reply, trace)

            # the model chose to act -- run every tool it asked for
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                result = call_tool(name, args)
                trace.steps.append(Step(step, name, args, _summarise_result(result)))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)[:4000],
                })

        # ran out of steps without a final answer
        trace.stopped_early = True
        messages.append({
            "role": "user",
            "content": "Stop searching. Give your JSON verdict now, based on what you have.",
        })
        try:
            reply = self.client.chat.completions.create(model=self.model, messages=messages)
            trace.raw_reply = reply.choices[0].message.content or ""
            return self._parse(cluster, trace.raw_reply, trace)
        except Exception as e:
            return self._fallback(cluster, f"LLM call failed after {self.max_steps} steps: {e}", trace)

    # -----------------------------------------------------------------
    def _parse(self, cluster: TrendCluster, text: str,
               trace: VerificationTrace) -> VerifiedTrend:
        """Turn the model's JSON reply into a VerifiedTrend."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return self._fallback(cluster, "model did not return valid JSON", trace)

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        evidence = []
        for e in data.get("evidence", []):
            if not isinstance(e, dict):
                continue
            tier = e.get("tier", "secondary")
            evidence.append(Evidence(
                source=str(e.get("source", "unknown")),
                tier="primary" if tier == "primary" else "secondary",
                url=str(e.get("url", "")),
                note=str(e.get("note", "")),
            ))

        # if the model cited nothing, fall back to the signals themselves so
        # the evidence trail is never empty
        if not evidence:
            evidence = [Evidence(source=s.source, tier=s.source_tier, url=s.url)
                        for s in cluster.signals]

        note = str(data.get("note", "")).strip() or "No explanation given."
        if trace.stopped_early:
            note += f" (Stopped after {self.max_steps} tool calls.)"

        return VerifiedTrend(cluster=cluster, confidence=confidence,
                              verification_note=note, evidence=evidence)

    def _fallback(self, cluster: TrendCluster, reason: str,
                  trace: VerificationTrace) -> VerifiedTrend:
        """
        Rule-based verdict when the model is unavailable or unparseable.
        Deliberately conservative: we would rather under-claim than invent
        confidence the agent never actually justified.
        """
        has_primary = "primary" in cluster.source_tiers
        n = cluster.independent_source_count

        if has_primary and n >= 2:
            conf = 0.8
        elif has_primary:
            conf = 0.65
        elif n >= 2:
            conf = 0.45
        else:
            conf = 0.2

        return VerifiedTrend(
            cluster=cluster, confidence=conf,
            verification_note=f"Fallback verdict ({reason}). Scored from source "
                              f"tiers only, without agent reasoning.",
            evidence=[Evidence(source=s.source, tier=s.source_tier, url=s.url)
                      for s in cluster.signals],
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    from clustering import cluster_signals, load_signals

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description="Verify clustered trends")
    ap.add_argument("--signals", default="01_data/signals.json")
    ap.add_argument("--index", type=int, help="verify only cluster N")
    ap.add_argument("--limit", type=int, default=3, help="how many clusters to verify")
    ap.add_argument("--verbose", action="store_true", help="show the tool-call trace")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("! OPENAI_API_KEY not set -- every trend will use the rule-based fallback.\n")

    clusters = cluster_signals(load_signals(args.signals))
    # biggest first: multi-signal clusters are the interesting ones
    clusters.sort(key=lambda c: -len(c.signals))

    chosen = [clusters[args.index]] if args.index is not None else clusters[:args.limit]
    agent = VerificationAgent()

    for c in chosen:
        trace = VerificationTrace()
        result = agent.run(c, trace)

        print(f"\n{'='*70}\n{c.representative_title[:68]}")
        print(f"{len(c.signals)} signal(s), {c.independent_source_count} independent source(s)")

        if args.verbose and trace.steps:
            print("\n  tool calls the agent chose to make:")
            for s in trace.steps:
                print(s)

        print(f"\n  confidence : {result.confidence}")
        print(f"  note       : {result.verification_note}")
        print(f"  evidence   : {len(result.evidence)} item(s)")
        for e in result.evidence[:4]:
            print(f"      [{e.tier}] {e.source} {('- ' + e.note) if e.note else ''}")


if __name__ == "__main__":
    main()
