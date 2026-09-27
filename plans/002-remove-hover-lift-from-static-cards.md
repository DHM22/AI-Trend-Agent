# 002 — Remove the hover lift from cards that aren't clickable

- **Status**: DONE (applied and feel-checked 2026-09-27)
- **Commit**: a81876c
- **Severity**: MEDIUM
- **Category**: Purpose & frequency
- **Estimated scope**: 1 file (`c_sync/ui_components.py`), 2 small edits in the `CSS` string

## Problem

Every `.sr-glass` card lifts 3px, brightens its border and deepens its shadow on
hover. None of them does anything when clicked: all 10 uses are plain `<div>`s
(`ui_components.py:168` and `:178`; `ui_pages.py:134`, `:236`, `:265`, `:269`,
`:273`, `:338`, `:364`, `:366`). Hover motion is a promise of interactivity;
here it's a false one, repeated on almost every page. It also animates
`box-shadow`, which repaints.

```css
/* c_sync/ui_components.py:38-39 — current (inside the CSS string) */
.sr-glass{background:linear-gradient(150deg,#1d2739e8,#101827dd);border:1px solid #ffffff20;border-radius:16px;padding:16px 18px;box-shadow:0 12px 36px #0003;transition:transform .25s,border-color .25s,box-shadow .25s}
.sr-glass:hover{transform:translateY(-3px);border-color:#9483c777;box-shadow:0 22px 55px #0007}
```

## Target

```css
/* static card: no transition, no hover state */
.sr-glass{background:linear-gradient(150deg,#1d2739e8,#101827dd);border:1px solid #ffffff20;border-radius:16px;padding:16px 18px;box-shadow:0 12px 36px #0003}
```

The `.sr-glass:hover{…}` rule is deleted entirely. `.sr-glass.selected{…}`
(the next rule) stays exactly as it is.

## Repo conventions to follow

- All C-sync CSS lives in ONE minified Python string, `CSS`, in
  `c_sync/ui_components.py`; rules sit one after another.
- **Never put a `<` inside the CSS**, not even in a comment.

## Steps

1. In `c_sync/ui_components.py`, in the `.sr-glass{…}` rule (line 38), delete
   `;transition:transform .25s,border-color .25s,box-shadow .25s` so the rule
   ends at `box-shadow:0 12px 36px #0003}`.
2. Delete the whole rule `.sr-glass:hover{transform:translateY(-3px);border-color:#9483c777;box-shadow:0 22px 55px #0007}` (line 39).

## Boundaries

- Do NOT change `.sr-glass.selected`, `.cs-dash`, or any other card style.
- Do NOT change markup, and do NOT make any card clickable.
- Leave the reduced-motion rule on line 97 alone (its `.sr-glass{transition:none}`
  becomes a harmless no-op).
- If the code doesn't match the excerpts (drift since `a81876c`), STOP and report.

## Verification

- **Mechanical**: `python 02_src/agents/test_chain.py` → no new failures.
  The stray-`<` check from plan 004 prints `0`.
- **Feel check**: restart Streamlit and move the mouse over the cards on
  **Trend story** (the trend card and the confidence stat) and **How it works**
  (the five step cards):
  - Nothing moves, brightens or grows a shadow on hover.
  - Real controls (buttons, radar lights, evidence cards) still react as before.
- **Done when**: `.sr-glass` has no `transition` and no `:hover` rule exists
  for it.
