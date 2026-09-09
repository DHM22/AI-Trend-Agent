"""
Tools the agents can call.
===========================
This is the boundary between "the model reasons" and "the model acts".

An agent does not fetch anything itself. It emits a tool call -- a small JSON
object naming a tool and its arguments -- and this module executes it and
hands back the result. The model then decides what to do next: answer, or
call another tool.

That loop is what makes the system agentic. We do not write the order of
calls; the model chooses at runtime based on what it has found so far.

Two tools, matching the two questions the pipeline asks:

    github_lookup     -> "is this claim real?"        (VerificationAgent)
    search_curriculum -> "do we teach this?"           (CurriculumAgent)

Every tool here:
  * returns a JSON-serialisable dict, never raises into the agent loop
  * reports failure as data ({"error": ...}) so the model can react to it
  * is safe to call repeatedly -- the agent WILL call them more than once
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

# scripts run from the repo root, so 02_src is not automatically importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import curriculum_ingest


DEFAULT_DB = "./vectorstore"
GITHUB_API = "https://api.github.com"
TIMEOUT = 15


# ---------------------------------------------------------------------------
# TOOL 1 -- github_lookup
#
# The verification question is usually "does this thing actually exist, and
# did the project really say this?" GitHub answers both: a repo that does not
# exist is a strong signal a claim is fabricated, and release notes are the
# project's own words.
# ---------------------------------------------------------------------------

def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def github_lookup(query: str, max_results: int = 3) -> dict:
    """
    Search GitHub repositories by name or keyword.

    Returns repo name, description, star count and last push date. Stars and
    recency matter for verification: a project with 40k stars pushed last week
    is established; one with 3 stars and no commits in two years is not
    evidence of a real trend, whatever the announcement claimed.
    """
    try:
        r = requests.get(f"{GITHUB_API}/search/repositories",
                         headers=_headers(),
                         params={"q": query, "sort": "stars", "per_page": max_results},
                         timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"error": f"network error: {e}", "query": query}

    if r.status_code == 403 and "rate limit" in r.text.lower():
        reset = r.headers.get("X-RateLimit-Reset")
        mins = ""
        if reset:
            mins = f", resets in ~{max(0, int(reset) - int(time.time())) // 60} min"
        return {"error": f"github rate limit reached{mins}. Set GITHUB_TOKEN in .env.",
                "query": query}

    if not r.ok:
        return {"error": f"github returned HTTP {r.status_code}", "query": query}

    items = r.json().get("items", [])
    if not items:
        # a real finding, not a failure -- "no such project" is evidence
        return {"query": query, "found": 0, "results": [],
                "note": "No matching repository. Treat claims about this as unverified."}

    return {
        "query": query,
        "found": len(items),
        "results": [{
            "full_name": it["full_name"],
            "description": (it.get("description") or "")[:200],
            "stars": it.get("stargazers_count", 0),
            "last_push": it.get("pushed_at", ""),
            "url": it.get("html_url", ""),
        } for it in items],
    }


# ---------------------------------------------------------------------------
# TOOL 2 -- search_curriculum
#
# Thin wrapper over the RAG store built in curriculum_ingest.py. The agent
# passes a natural-language question; hybrid search handles both meaning and
# exact identifiers.
# ---------------------------------------------------------------------------

def search_curriculum(question: str, week: int | None = None,
                      content_type: str | None = None,
                      max_results: int = 3,
                      db_path: str = DEFAULT_DB) -> dict:
    """
    Search the ingested course slides and lab notebooks.

    Each hit carries a citation ("Week 2 / RAG Introduction / slide 34") and
    an is_reliable flag. The flag exists because similarity alone is not
    trustworthy here: measured on our own decks, a slide literally containing
    "FAISS" scored 0.303 while an unrelated slide scored 0.308. An exact
    identifier match is reliable regardless of the number.
    """
    try:
        hits = curriculum_ingest.query(db_path, question, k=max_results,
                                        week=week, content_type=content_type)
    except Exception as e:
        return {"error": f"curriculum search failed: {e}", "question": question}

    if not hits:
        return {"question": question, "found": 0, "results": [],
                "note": "Nothing in the curriculum matches. The trend may be "
                        "real but outside what we teach."}

    results = []
    for h in hits:
        exact = h.get("exact_match")
        sim = h.get("similarity")
        results.append({
            "citation": h["citation"],
            "week": h.get("week"),
            "content_type": h.get("content_type", "slides"),
            "text": h["text"][:400],
            "similarity": sim,
            "exact_match": exact,
            "is_reliable": exact is not None or (sim or 0) >= RELEVANCE_FLOOR,
        })

    return {"question": question, "found": len(results), "results": results}


# keep in sync with schemas.RELEVANCE_FLOOR -- imported lazily to avoid a
# circular import if schemas ever needs anything from here
try:
    from schemas import RELEVANCE_FLOOR
except ImportError:
    RELEVANCE_FLOOR = 0.48


# ---------------------------------------------------------------------------
# TOOL SCHEMAS
#
# This is what the model actually sees. The `description` fields are not
# documentation -- they are the prompt. The model decides whether to call a
# tool based entirely on this text, so it should say WHEN to use the tool,
# not just what it does.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "github_lookup",
            "description": (
                "Search GitHub repositories to check whether a project or tool "
                "actually exists and how established it is. Use this when a claim "
                "mentions a specific library, framework or repository and you need "
                "to confirm it is real before trusting the claim. Returns star "
                "counts and last push date, which indicate whether a project is "
                "widely adopted or abandoned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Repository name or keywords, e.g. 'langchain' "
                                       "or 'RapidAgent framework'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "How many repositories to return. Default 3.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_curriculum",
            "description": (
                "Search our course slides and lab notebooks to find out whether we "
                "already teach something. Use this to decide if a technology trend "
                "affects our curriculum. Returns specific slides or notebook cells "
                "with citations. Prefer specific technical terms in the question "
                "(library names, class names, API methods) over general phrasing, "
                "because exact identifier matches are more reliable than topical "
                "similarity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "What to look for, e.g. 'AgentExecutor' or "
                                       "'how do we teach chunking'.",
                    },
                    "week": {
                        "type": "integer",
                        "description": "Restrict to one week's material. Omit to search all.",
                    },
                    "content_type": {
                        "type": "string",
                        "enum": ["slides", "lab"],
                        "description": "Restrict to lecture slides or lab notebooks. "
                                       "Use 'lab' when checking whether code would break.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "How many results to return. Default 3.",
                    },
                },
                "required": ["question"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# DISPATCH
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "github_lookup": github_lookup,
    "search_curriculum": search_curriculum,
}


def call_tool(name: str, arguments: dict | str) -> dict:
    """
    Execute a tool call from the model and return the result.

    Never raises. A tool that blows up returns {"error": ...} so the model can
    read the failure and decide what to do -- try a different query, or give
    up and report low confidence. An exception here would kill the agent loop
    instead, which loses that reasoning.
    """
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError as e:
            return {"error": f"could not parse arguments: {e}"}

    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"unknown tool '{name}'. "
                         f"Available: {', '.join(TOOL_FUNCTIONS)}"}

    try:
        return func(**arguments)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{name} failed: {type(e).__name__}: {e}"}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Try a tool by hand")
    ap.add_argument("tool", choices=list(TOOL_FUNCTIONS))
    ap.add_argument("query")
    ap.add_argument("--week", type=int)
    ap.add_argument("--type", dest="content_type", choices=["slides", "lab"])
    args = ap.parse_args()

    if args.tool == "github_lookup":
        out = call_tool("github_lookup", {"query": args.query})
    else:
        out = call_tool("search_curriculum", {
            "question": args.query, "week": args.week,
            "content_type": args.content_type})

    print(json.dumps(out, indent=2, ensure_ascii=False))