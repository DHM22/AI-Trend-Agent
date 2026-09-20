#!/usr/bin/env bash
# Run the VerificationAgent against the test signals.
#
#   ./run_verify.sh            # agentic demo (LLM-driven loop; needs OPENAI_API_KEY)
#   ./run_verify.sh --cache    # replay fully from cache: deterministic, no network
#
# GITHUB_TOKEN and OPENAI_API_KEY are read from .env (sourced below). GitHub
# responses are cached under 01_data/.tool_cache, so a warm cache lets the demo
# run offline -- see the RESPONSE CACHE notes in 02_src/agents/tools.py.
set -euo pipefail
cd "$(dirname "$0")"

# load OPENAI_API_KEY / GITHUB_TOKEN from .env
set -a
. ./.env
set +a

if [[ "${1:-}" == "--cache" ]]; then
  # Fully-from-cache demo: no model, no network. The tool loop serves every
  # GitHub response from disk; a warm cache is required (run without --cache once).
  export TOOL_CACHE_ONLY=1
  unset OPENAI_API_KEY
fi

.venv/bin/python 02_src/agents/verification.py \
  --signals 01_data/test_signals.json \
  --model gpt-5.4-mini \
  --show-reasoning
