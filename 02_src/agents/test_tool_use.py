"""
Does the VerificationAgent actually USE its tools?
===================================================
Real signals are all plausible, so the agent can score them from the text
alone and never reach for a tool. That leaves an open question: would it call
one if it needed to?

This feeds it three cases where the answer should differ, and reports whether
tools were called in each. Run from the repo root:

    python 02_src/agents/test_tool_use.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from schemas import RawSignal, TrendCluster
from agents.verification import VerificationAgent, VerificationTrace


CASES = [
    (
        "FABRICATED -- should call a tool and find nothing",
        TrendCluster(
            "New framework 'VelocityAgent' claims 12x faster tool calling than LangChain",
            [RawSignal(
                title="New framework 'VelocityAgent' claims 12x faster tool calling than LangChain",
                source="tweet", source_tier="secondary",
                summary="A tweet thread claims VelocityAgent outperforms LangChain on tool "
                        "dispatch by 12x. No benchmarks, no repository linked, no other "
                        "coverage anywhere.",
                url="", published="2026-09-05T00:00:00Z")],
        ),
    ),
    (
        "REAL BUT UNCITED -- claim about a project the signal does not link",
        TrendCluster(
            "Blog post says LangGraph now supports durable execution",
            [RawSignal(
                title="Blog post says LangGraph now supports durable execution",
                source="random_blog", source_tier="secondary",
                summary="An independent blog claims LangGraph added durable execution. "
                        "No link to a release, no official announcement referenced.",
                url="", published="2026-09-05T00:00:00Z")],
        ),
    ),
    (
        "SELF-EVIDENT -- primary source in hand, a tool call would be redundant",
        TrendCluster(
            "langchain-ai/langchain: langchain==1.4.0",
            [RawSignal(
                title="langchain-ai/langchain: langchain==1.4.0",
                source="github", source_tier="primary",
                summary="Changes since langchain==1.3.18 docs(langchain): runnable "
                        "`langchain.mcp` examples (#39976)",
                url="https://github.com/langchain-ai/langchain/releases/tag/langchain%3D%3D1.4.0",
                published="2026-09-03T00:00:00Z")],
        ),
    ),
]


def main():
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set -- this test needs it to mean anything.")
        return

    agent = VerificationAgent()

    for label, cluster in CASES:
        trace = VerificationTrace()
        result = agent.run(cluster, trace)

        print(f"\n{'=' * 72}")
        print(label)
        print(f"  {cluster.representative_title[:66]}")
        print(f"{'-' * 72}")

        if trace.steps:
            print(f"  TOOLS CALLED: {len(trace.steps)}")
            for s in trace.steps:
                print(s)
        else:
            print("  TOOLS CALLED: none -- answered from the signal text alone")

        print(f"\n  confidence : {result.confidence}")
        print(f"  note       : {result.verification_note}")

    print(f"\n{'=' * 72}")
    print("WHAT TO CONCLUDE")
    print("""
  Case 1 SHOULD call a tool. VelocityAgent does not exist, and the only way
  to know that is to look. If the agent scores it low WITHOUT looking, it is
  guessing from tone rather than verifying -- right answer, wrong reasoning,
  and it will guess wrong on a real project that happens to sound hyped.

  Case 2 SHOULD probably call a tool. The claim is plausible but uncited.

  Case 3 reasonably needs no tool: the signal IS the primary source.

  If no case triggers a tool call, the system prompt needs to be more
  directive -- e.g. "if a claim names a project you have not confirmed
  exists, call github_lookup before scoring."
""")


if __name__ == "__main__":
    main()
