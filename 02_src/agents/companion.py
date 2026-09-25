"""
Instructor Companion Agent
==========================
A conversational layer over ONE recorded recommendation. An instructor asks
"why this tier?", "what did verification check?", "which lab cell is hit?",
and the companion answers from what the run recorded -- the recommendation,
its evidence, its curriculum match, and its agent trace.

It explains; it never decides. The tier, confidence and scores are the
recorded ones. The companion cannot change them and is told never to
recompute or overrule them -- a human approves every recommendation.

Follow-up lookups use the pipeline's own tools:
  * search_curriculum -- the local vector store, no API key
  * github_lookup / verify_release -- CACHE ONLY: the companion never touches
    the GitHub network, it can only re-read what earlier runs fetched

The three curriculum outcomes stay distinct (see CLAUDE.md, "Three curriculum
outcomes"): searched, search FAILED, and skipped. A failed search is never
described as "no coverage found" -- collapsing them is the original bug.

Usage:
    from agents.companion import CompanionAgent
    reply = CompanionAgent().answer(record, "Why is this update_existing_material?")

    # offline / testing: inject a fake OpenAI client and/or a fake tool runner
    CompanionAgent(client=fake, tool_runner=fake_dispatch).answer(record, question)
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parents[1])
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agents import tools
from demo_snapshot import SEARCH_FAILED_BANNER, TIER_LABEL, verification_mode_text


MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_TOOL_ROUNDS = 4          # follow-up lookups per question; the record carries most answers
MAX_HISTORY_TURNS = 6        # earlier Q/A pairs sent back with a new question
DEFAULT_DB = str(Path(__file__).resolve().parents[2] / "vectorstore")

COMPANION_TOOLS = ("search_curriculum", "github_lookup", "verify_release")
_TOOL_SCHEMAS = [s for s in tools.TOOL_SCHEMAS if s["function"]["name"] in COMPANION_TOOLS]

MODE_MODEL = "model"
MODE_OFFLINE = "offline"
MODE_ERROR = "error"


# ---------------------------------------------------------------------------
# CURRICULUM OUTCOME -- the tri-state, never collapsed
# ---------------------------------------------------------------------------

SEARCHED, SEARCH_FAILED, SKIPPED, NO_TRACE = "searched", "search_failed", "skipped", "no_trace"


def curriculum_state(record: dict) -> tuple[str, str]:
    """(state, plain-language line) for the recorded curriculum search."""
    trace = record.get("trace") if isinstance(record, dict) else None
    c = (trace or {}).get("curriculum") if isinstance(trace, dict) else None
    if not isinstance(c, dict):
        return NO_TRACE, ("No curriculum trace was recorded for this recommendation, so "
                          "whether a search ran is unknown.")
    if c.get("search_failed") is True:
        reason = c.get("reason") or "no reason recorded"
        return SEARCH_FAILED, f"{SEARCH_FAILED_BANNER} Failure: {reason}"
    if c.get("searched") is False:
        return SKIPPED, ("The curriculum search was SKIPPED (never attempted): "
                         + (c.get("skipped_reason") or "it did not clear the confidence gate."))
    return SEARCHED, ("The curriculum WAS searched. Its conclusion: "
                      + (c.get("reason") or "no conclusion recorded."))


# ---------------------------------------------------------------------------
# CONTEXT -- everything the run recorded about one recommendation
# ---------------------------------------------------------------------------

def record_context(record: dict) -> str:
    """The recorded facts about one recommendation, as the model will see them."""
    action = record.get("recommended_action") or ""
    lines = [
        f"TREND: {record.get('trend') or 'untitled'}",
        f"RECOMMENDED ACTION (recorded, final until a human changes it): "
        f"{TIER_LABEL.get(action, action) or 'none recorded'}",
        f"VERIFICATION CONFIDENCE (computed by code, not a model): {record.get('confidence')}",
        f"VERIFICATION NOTE: {record.get('verification_note') or 'none'}",
        f"TOTAL SCORE (0.5 maturity + 0.5 relevance, out of 5): {record.get('total_score')}",
    ]

    evidence = record.get("evidence") or []
    lines.append(f"\nEVIDENCE ({len(evidence)} item(s)):")
    for i, ev in enumerate(evidence, 1):
        lines.append(f"  [{i}] {ev.get('source')}/{ev.get('tier')} {ev.get('kind') or ''}: "
                     f"{ev.get('note') or ''} <{ev.get('url') or 'no url'}>")

    match = record.get("match")
    if match:
        lines += [
            "\nCURRICULUM MATCH:",
            f"  citation: {match.get('citation')}",
            f"  content type: {match.get('content_type')} (a lab cell is more urgent than a slide)",
            f"  exact identifier: {match.get('exact_match') or 'none'}; similarity: {match.get('similarity')}",
            f"  matched text: {(match.get('matched_text') or '')[:600]}",
        ]
    else:
        lines.append("\nCURRICULUM MATCH: none recorded")

    state, text = curriculum_state(record)
    lines.append(f"\nCURRICULUM OUTCOME [{state}]: {text}")

    plan = record.get("action_plan") or []
    if plan:
        lines.append("\nACTION PLAN:")
        lines += [f"  {n}. {step}" for n, step in enumerate(plan, 1)]

    trace = record.get("trace") if isinstance(record.get("trace"), dict) else {}
    v = trace.get("verification") or {}
    if v:
        lines.append(f"\nVERIFICATION TRACE ({verification_mode_text(v.get('mode', '')) or 'mode unknown'}):")
        for s in v.get("steps") or []:
            lines.append(f"  step {s.get('n')}: {s.get('tool')}({json.dumps(s.get('arguments') or {})}) "
                         f"-> {s.get('result_summary')}")
        if v.get("stopped_early"):
            lines.append("  (verification hit its step limit before the model stopped)")
    c = trace.get("curriculum") or {}
    if c.get("steps"):
        lines.append("\nCURRICULUM SEARCH TRACE:")
        for s in c["steps"]:
            lines.append(f"  step {s.get('n')}: query {s.get('query')!r} filters "
                         f"{json.dumps(s.get('filters') or {})} -> {s.get('result_summary')}")
    if not trace:
        lines.append("\nAGENT TRACE: none recorded (a pre-trace snapshot)")
    return "\n".join(lines)


SYSTEM_PROMPT = """You are the Instructor Companion for C-Sync, a system that watches AI-library
releases and blog posts and recommends curriculum changes for a WeCloudData course.

An instructor is asking about ONE recorded recommendation. Everything the run recorded
about it is below. Answer from that record, and from tool results you fetch, only.

Rules:
1. The recommended action, confidence and scores are FINAL as recorded. Explain them;
   never recompute, re-rank or overrule them, and never say what the tier "should" be.
   Only a human approves or changes a recommendation.
2. Cite what you rely on: evidence as [n], course material by its citation
   (e.g. "Week 3 / Lab: ... / cell 36"), tool results by the tool name.
3. Keep the curriculum outcome exact. If the search FAILED, say it failed and that this
   is NOT evidence the topic is uncovered. If it was SKIPPED, say it never ran. Only a
   search that ran can support "the course does not cover this".
4. If the record does not contain the answer, say so. Do not fill gaps from memory
   about libraries, releases or dates.
5. Tools: search_curriculum re-searches the course material. github_lookup and
   verify_release only re-read cached results from earlier runs; a cache miss means
   "not checked", never "does not exist".
6. Be brief: a few sentences or a short list. Plain language for instructors.

RECORD:
{context}
"""


# ---------------------------------------------------------------------------
# TOOLS -- the pipeline's own, GitHub forced cache-only
# ---------------------------------------------------------------------------

def companion_tool_runner(name: str, arguments: dict | str, db_path: str = DEFAULT_DB) -> dict:
    """Run one companion tool. Never raises; never touches the GitHub network."""
    if name not in COMPANION_TOOLS:
        return {"error": f"tool '{name}' is not available to the companion"}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError as e:
            return {"error": f"could not parse arguments: {e}"}
    if name == "search_curriculum":
        args = {k: v for k, v in arguments.items() if k in ("question", "week", "max_results")}
        if not str(args.get("question", "")).strip():
            return {"error": "search_curriculum needs a question"}
        return tools.search_curriculum(db_path=db_path, **args)
    saved = os.environ.get("TOOL_CACHE_ONLY")
    os.environ["TOOL_CACHE_ONLY"] = "1"
    try:
        return tools.call_tool(name, arguments)
    finally:
        if saved is None:
            os.environ.pop("TOOL_CACHE_ONLY", None)
        else:
            os.environ["TOOL_CACHE_ONLY"] = saved


def _summarise(result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)[:200]
    if result.get("error"):
        return f"error: {result['error']}"
    if "results" in result:
        cites = [r.get("citation") for r in result.get("results") or []]
        return f"{result.get('found', len(cites))} hit(s): " + " | ".join(c for c in cites if c)
    return json.dumps(result)[:200]


# ---------------------------------------------------------------------------
# AGENT
# ---------------------------------------------------------------------------

@dataclass
class CompanionReply:
    text: str
    mode: str                                   # MODE_MODEL / MODE_OFFLINE / MODE_ERROR
    tool_calls: list[dict] = field(default_factory=list)   # {"tool", "arguments", "summary"}
    stopped_early: bool = False


class CompanionAgent:
    """Answers an instructor's questions about one recorded recommendation."""

    def __init__(self, client=None, model: str = MODEL, tool_runner=None,
                 max_tool_rounds: int = MAX_TOOL_ROUNDS, db_path: str = DEFAULT_DB):
        self._client = client
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self._run_tool = tool_runner or (lambda n, a: companion_tool_runner(n, a, db_path))

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        self._client = OpenAI()
        return self._client

    def available(self) -> bool:
        """True when a model can answer (a client was given or a key is set)."""
        return self._get_client() is not None

    def answer(self, record: dict, question: str,
               history: list[tuple[str, str]] = ()) -> CompanionReply:
        client = self._get_client()
        if client is None:
            return offline_reply(record)
        try:
            return self._loop(client, record, question, history)
        except Exception as e:
            return CompanionReply(
                text=(f"The model call failed ({type(e).__name__}), so there is no answer to "
                      "this question. Nothing about the recommendation has changed; its recorded "
                      "evidence is still on the Trend story and Decision pages."),
                mode=MODE_ERROR)

    def _loop(self, client, record: dict, question: str,
              history: list[tuple[str, str]]) -> CompanionReply:
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=record_context(record))}]
        for q, a in list(history)[-MAX_HISTORY_TURNS:]:
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        messages.append({"role": "user", "content": question})

        calls = []
        for round_n in range(self.max_tool_rounds + 1):
            last_round = round_n == self.max_tool_rounds   # no tools offered: must answer
            kwargs = {} if last_round else {"tools": _TOOL_SCHEMAS, "tool_choice": "auto"}
            resp = client.chat.completions.create(model=self.model, messages=messages,
                                                  temperature=0, **kwargs)
            msg = resp.choices[0].message
            if not msg.tool_calls or last_round:
                return CompanionReply(text=(msg.content or "").strip() or "(no answer returned)",
                                      mode=MODE_MODEL, tool_calls=calls,
                                      stopped_early=bool(msg.tool_calls))
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if tc.function.name in COMPANION_TOOLS:
                    result = self._run_tool(tc.function.name, args)
                else:
                    result = {"error": f"tool '{tc.function.name}' is not available to the companion"}
                calls.append({"tool": tc.function.name, "arguments": args,
                              "summary": _summarise(result)})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result)[:6000]})
        raise AssertionError("unreachable: the last round offers no tools")


def offline_reply(record: dict) -> CompanionReply:
    """No model available: say so, and restate the recorded facts -- nothing more."""
    action = record.get("recommended_action") or ""
    match = record.get("match") or {}
    _, outcome = curriculum_state(record)
    parts = [
        "The companion needs an OpenAI key (OPENAI_API_KEY) to answer questions. "
        "Here is what the recorded run says:",
        f"- Recommended action: {TIER_LABEL.get(action, action) or 'none recorded'}",
        f"- Verification: {record.get('verification_note') or 'no note recorded'}",
        f"- Course material: {match.get('citation') or 'no match recorded'}",
        f"- Curriculum search: {outcome}",
    ]
    return CompanionReply(text="\n".join(parts), mode=MODE_OFFLINE)
