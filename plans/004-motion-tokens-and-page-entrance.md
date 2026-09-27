# 004 — Add motion tokens and speed up the page-entrance animation

- **Status**: DONE (applied and feel-checked 2026-09-27)
- **Commit**: a81876c
- **Severity**: MEDIUM
- **Category**: Easing & duration (plus Cohesion & tokens)
- **Estimated scope**: 1 file (`c_sync/ui_components.py`), 2 small edits inside the `CSS` string

## Problem

C-sync has no shared motion values, and every element on every page fades and
slides in with the weak built-in `ease` over 380ms, above the 300ms budget for
UI motion. Page changes happen dozens of times per session (sidebar, stage bar,
"Next" buttons), so this slow entrance is felt constantly.

```css
/* c_sync/ui_components.py:14 — current (inside the CSS string) */
:root{--bg:#080c17;--panel:#111827;--line:#26344a;--text:#f0f4ff;--muted:#a7b5cc;--violet:#a78bfa;--cyan:#67e8f9;--green:#34d399;--amber:#fbbf24;--rose:#f0abfc}

/* c_sync/ui_components.py:81-82 — current */
@keyframes cs-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]{animation:cs-in .38s ease both}
```

## Target

```css
/* :root gains four motion tokens (keep every existing token as it is) */
:root{--bg:#080c17;--panel:#111827;--line:#26344a;--text:#f0f4ff;--muted:#a7b5cc;--violet:#a78bfa;--cyan:#67e8f9;--green:#34d399;--amber:#fbbf24;--rose:#f0abfc;--ease-out:cubic-bezier(0.23, 1, 0.32, 1);--ease-in-out:cubic-bezier(0.77, 0, 0.175, 1);--dur-press:160ms;--dur-ui:200ms}

/* page entrance: 200ms, strong ease-out. The cs-in keyframes stay unchanged. */
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]{animation:cs-in var(--dur-ui) var(--ease-out) both}
```

## Repo conventions to follow

- All C-sync CSS lives in ONE Python string, `CSS = """<style>…</style>"""`, in
  `c_sync/ui_components.py`. Rules are written minified, one after another. Edit
  the string in place; do not create a stylesheet file.
- Tokens already live on `:root` at `c_sync/ui_components.py:14` (`--violet`,
  `--cyan`, …). Add the motion tokens to that same rule.
- **Never put a `<` character anywhere inside the CSS**, not even in a
  `/* comment */`. Streamlit's HTML sanitizer drops the whole `<style>` block if
  it finds one, and every page loses its styling. Keep explanations in Python
  `#` comments outside the string.

## Steps

1. In `c_sync/ui_components.py`, in the `:root{…}` rule at line 14, append
   `;--ease-out:cubic-bezier(0.23, 1, 0.32, 1);--ease-in-out:cubic-bezier(0.77, 0, 0.175, 1);--dur-press:160ms;--dur-ui:200ms`
   just before its closing `}` (so the rule reads exactly as in Target).
2. At line 82, replace `animation:cs-in .38s ease both` with
   `animation:cs-in var(--dur-ui) var(--ease-out) both`.

## Boundaries

- Do NOT change `@keyframes cs-in` itself.
- Do NOT touch the reduced-motion rules (lines 97-98); they already turn this
  entrance off.
- Do NOT change any other rule, markup or Python code.
- If the lines above don't match the code you find (drift since `a81876c`),
  STOP and report instead of improvising.

## Verification

- **Mechanical** (from the repo root):
  - `python 02_src/agents/test_chain.py` → `228 passed, 0 failed` (or more passed; never a new failure).
  - `python -c "import sys; sys.path.insert(0,'c_sync'); import ui_components as u; b=u.CSS.strip(); print(b[7:-8].count('<'))"` → `0`.
- **Feel check**: restart Streamlit (`python -m streamlit run c_sync/app.py`; it
  does not hot-reload), then switch pages several times from the sidebar:
  - The new page appears almost at once and settles in about 0.2s, with no
    slow, floaty drift.
  - In DevTools › Animations, set playback to 10% and confirm the motion starts
    fast and decelerates (strong ease-out), never slow-then-fast.
  - In DevTools › Rendering, emulate `prefers-reduced-motion: reduce` and
    confirm pages appear with no slide at all.
- **Done when**: the four tokens exist on `:root`, the entrance rule uses them,
  tests pass, and the stray-`<` check prints `0`.
