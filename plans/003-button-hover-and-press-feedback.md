# 003 — Calm button hover, add press feedback, gate hover to mice

- **Status**: DONE (applied and feel-checked 2026-09-27)
- **Commit**: a81876c
- **Severity**: MEDIUM
- **Category**: Purpose & frequency, Accessibility, Physicality
- **Estimated scope**: 1 file (`c_sync/ui_components.py`), edits inside the `CSS` string
- **Depends on**: plan 004 (it adds `--ease-out` and `--dur-press` to `:root`)

## Problem

Every Streamlit button (including the 9 sidebar menu items and the 5 stage-bar
buttons, passed over dozens of times a session) jumps up 2px and grows a
shadow on hover. That's too much motion for such frequent contact. The hover
isn't limited to real pointers, so on touch screens a tap fires a false hover
and a button can stay "lifted". And there is no feedback on press at all.

```css
/* c_sync/ui_components.py:20-21 — current (inside the CSS string) */
[data-testid="stButton"] button{border-radius:10px;min-height:36px;font-weight:650;transition:transform .2s,box-shadow .2s,border-color .2s}
[data-testid="stButton"] button:hover{transform:translateY(-2px);box-shadow:0 10px 25px #0005;border-color:#7c8fab}

/* c_sync/ui_components.py:97 — current, inside the first reduced-motion block */
.sr-glass,[data-testid="stButton"] button{transition:none}
```

## Target

```css
/* base: only the press transform animates; border colour eases gently */
[data-testid="stButton"] button{border-radius:10px;min-height:36px;font-weight:650;transition:transform var(--dur-press) var(--ease-out),border-color 150ms ease}
/* hover only where a real mouse exists: colour change, no movement, no shadow */
@media (hover:hover) and (pointer:fine){[data-testid="stButton"] button:hover{border-color:#7c8fab}}
/* press feedback */
[data-testid="stButton"] button:active{transform:scale(0.97)}
```

And in the FIRST reduced-motion block (line 97), keep the colour feedback but
drop movement, by adding this rule inside that block:

```css
[data-testid="stButton"] button:active{transform:none}
```

## Repo conventions to follow

- All C-sync CSS lives in ONE minified Python string, `CSS`, in
  `c_sync/ui_components.py`; rules sit one after another. A `@media` block is
  written inline the same way (see line 96: `@media(max-width:850px){…}`).
- Motion tokens on `:root` after plan 004: `--ease-out:cubic-bezier(0.23, 1, 0.32, 1)`,
  `--dur-press:160ms`. Use them with `var(…)`.
- **Never put a `<` inside the CSS**, not even in a comment.

## Steps

1. Confirm plan 004 is done (`:root` contains `--ease-out` and `--dur-press`).
   If not, STOP and do plan 004 first.
2. Replace line 20's rule with the Target's first rule
   (`transition:transform var(--dur-press) var(--ease-out),border-color 150ms ease`).
3. Replace line 21's `[data-testid="stButton"] button:hover{…}` rule with the
   Target's `@media (hover:hover) and (pointer:fine){…}` rule followed by the
   `:active` rule.
4. In the reduced-motion block on line 97
   (`@media(prefers-reduced-motion:reduce){…}`), add
   `[data-testid="stButton"] button:active{transform:none}` just before the
   block's final `}`. Leave that block's existing
   `.sr-glass,[data-testid="stButton"] button{transition:none}` as it is.

## Boundaries

- Do NOT touch the sidebar-specific button rule at line 77
  (`[data-testid="stSidebar"] [data-testid="stButton"] button{…}`), the primary
  gradient rule, or the `:focus-visible` outline rule near the end of the CSS.
- Do NOT change markup or Python.
- If the code doesn't match the excerpts (drift since `a81876c`), STOP and report.

## Verification

- **Mechanical**: `python 02_src/agents/test_chain.py` → no new failures.
  The stray-`<` check from plan 004 prints `0`.
- **Feel check**: restart Streamlit.
  - Desktop: hover sidebar and stage-bar buttons. Only the border colour
    changes; nothing jumps or casts a shadow.
  - Press and hold a button: it shrinks slightly (to 97%) at once and springs
    back on release. DevTools › Animations at 10%: the press starts fast and
    decelerates, and takes about 160ms.
  - Phone (DevTools device mode with touch): tapping a button shows the press,
    and no button stays in a hover state afterwards.
  - With `prefers-reduced-motion: reduce`: pressing gives no shrink; the
    border colour still changes on hover.
  - Keyboard: Tab to a button; the solid focus outline still shows.
- **Done when**: no `translateY` or `box-shadow` remains on button hover, the
  hover is inside the `(hover:hover) and (pointer:fine)` query, and `:active`
  scales to `0.97`.
