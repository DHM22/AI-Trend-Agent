# 001 — Make the evidence cards appear fast, with a short stagger

- **Status**: DONE (applied and feel-checked 2026-09-27)
- **Commit**: a81876c
- **Severity**: HIGH
- **Category**: Purpose & frequency, Easing & duration
- **Estimated scope**: 2 files, 1 small edit each
- **Depends on**: plan 004 (it adds `--ease-out` and `--dur-ui` to `:root`)

## Problem

The verification evidence cards start fully invisible (`opacity:0`) and rise in
one after another: each waits `0.35 × its index` seconds, then animates for
0.5s with the weak built-in `ease`. With 4 cards, the last one only shows about
1.55s after the page opens. These cards are the content on Trend story (and in
expanders on Evaluation and Decision), so every visit hides the thing the user
came to read for over a second. Stagger is decorative and must never block
reading; the budget is 30–80ms between items.

```css
/* c_sync/ui_components.py:98 — current (inside the CSS string) */
.cs-ev details{background:#111b2bdc;border:1px solid #ffffff18;border-left:3px solid var(--ev,#5b6b86);border-radius:12px;opacity:0;animation:cs-rise .5s ease forwards}
```

```python
# c_sync/ui_pages.py:121 — current
f'<details class="{state}" style="animation-delay:{0.35 * index:.2f}s">'
```

## Target

```css
/* each card: 200ms, strong ease-out (tokens from plan 004) */
.cs-ev details{background:#111b2bdc;border:1px solid #ffffff18;border-left:3px solid var(--ev,#5b6b86);border-radius:12px;opacity:0;animation:cs-rise var(--dur-ui) var(--ease-out) forwards}
```

```python
# 40ms stagger: 4 cards are all visible within 0.32s
f'<details class="{state}" style="animation-delay:{0.04 * index:.2f}s">'
```

## Repo conventions to follow

- All C-sync CSS lives in ONE minified Python string, `CSS`, in
  `c_sync/ui_components.py`. Edit the rule in place.
- Motion tokens live on `:root` at `c_sync/ui_components.py:14` after plan 004:
  `--ease-out:cubic-bezier(0.23, 1, 0.32, 1)` and `--dur-ui:200ms`. Use them
  with `var(…)`; do not type the curve again.
- **Never put a `<` inside the CSS**, not even in a comment: Streamlit's
  sanitizer then drops the whole stylesheet.

## Steps

1. Confirm plan 004 is done: `:root` in `c_sync/ui_components.py` contains
   `--ease-out` and `--dur-ui`. If not, STOP and do plan 004 first.
2. In `c_sync/ui_components.py`, in the `.cs-ev details{…}` rule (line 98),
   replace `animation:cs-rise .5s ease forwards` with
   `animation:cs-rise var(--dur-ui) var(--ease-out) forwards`.
3. In `c_sync/ui_pages.py:121`, change `{0.35 * index:.2f}` to
   `{0.04 * index:.2f}`.

## Boundaries

- Do NOT change `@keyframes cs-rise`: `.cs-reveal` (the Evaluation score rings)
  uses it too, and its slower reveal is deliberate.
- Do NOT change `.cs-reveal`, `score_ring`, or the reduced-motion rule for
  `.cs-ev details` (line 98 already sets `animation:none; opacity:1` there).
- Do NOT change markup other than the one number on `ui_pages.py:121`.
- If the code doesn't match the excerpts (drift since `a81876c`), STOP and report.

## Verification

- **Mechanical**: `python 02_src/agents/test_chain.py` → no new failures
  (228 passed at the time of writing). The stray-`<` check from plan 004 prints `0`.
- **Feel check**: restart Streamlit, open **Trend story** for
  `langchain-core==1.6.4` (4 evidence cards):
  - All four cards are visible within about a third of a second; you can start
    reading the first one immediately.
  - The cascade is still perceptible as a quick ripple, not a slow sequence.
  - DevTools › Animations at 10%: each card starts fast and decelerates; the
    gap between cards is small and even.
  - With `prefers-reduced-motion: reduce` emulated, all cards appear at once
    with no movement.
- **Done when**: the rule uses the tokens, the delay factor is `0.04`, and the
  4th card is fully visible ≈0.32s after the page renders (was ≈1.55s).
