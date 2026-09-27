# Animation plans

Written by the `improve-animations` skill (Emil Kowalski's animation
principles) from an audit of `c_sync/` at commit `a81876c`. Each plan is
self-contained: an agent or a person can execute it without this conversation.
The audit changed no source code.

| # | Plan | Severity | Status |
|---|---|---|---|
| 004 | [Add motion tokens and speed up the page entrance](004-motion-tokens-and-page-entrance.md) | MEDIUM | DONE |
| 001 | [Make the evidence cards appear fast, with a short stagger](001-evidence-cards-appear-fast.md) | HIGH | DONE |
| 003 | [Calm button hover, add press feedback, gate hover to mice](003-button-hover-and-press-feedback.md) | MEDIUM | DONE |
| 002 | [Remove the hover lift from cards that aren't clickable](002-remove-hover-lift-from-static-cards.md) | MEDIUM | DONE |

## Execution order

1. **004 first.** It adds `--ease-out`, `--ease-in-out`, `--dur-press` and
   `--dur-ui` to `:root`; 001 and 003 use them.
2. **001**, then **003** (both depend on 004).
3. **002** has no dependencies and can go at any point.

All four edit the single `CSS` string in `c_sync/ui_components.py`, so run
them one after another, not in parallel. After each, restart Streamlit (it does
not hot-reload `ui_*.py`) and run `python 02_src/agents/test_chain.py`.

**Warning for every plan:** never put a `<` character inside the CSS, not even
in a comment. Streamlit's sanitizer then drops the whole stylesheet.

## Not planned (from the same audit)

- #5 Stale-rerun dimming to 15% (`[data-stale="true"]`): needs a feel check on
  quick widget clicks before deciding.
- #6 Radar light hover not limited to mouse pointers (LOW).
- #7 Replace the remaining hand-typed durations with the new tokens (LOW).
- #8 Delete the unused old-radar CSS and `pipeline()` (LOW).
- Missed opportunities: animated evidence-card expansion, a soft fade when the
  Dashboard filter removes cards, a fade-in for new Ask answers.
