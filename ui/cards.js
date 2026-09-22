/*
  Shared recommendation-card and agent-trace renderers.
  ====================================================
  Used by advanced.html (the dashboard) and walkthrough.html (the presenter
  page), so the walkthrough shows a card EXACTLY as the dashboard does -- one
  copy of the rendering, same reason theme.css is one copy of the palette.
  Moved verbatim out of advanced.html; the only change is that card() takes
  the tier list as a parameter instead of reading the dashboard's global.
  Plain script (no build step): defines globals esc, TIER_VAR, card, traceBlock.
*/

const TIER_VAR = {
  update_existing_material: "--tier-1",
  add_new_lesson:           "--tier-2",
  add_optional_content:     "--tier-3",
  investigate_larger_change:"--tier-4",
  watch:                    "--tier-5",
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function confidenceWords(c) {
  if (typeof c !== "number") return ["var(--text-muted)", "n/a"];
  if (c >= 0.85) return ["var(--good)", "strong"];
  if (c >= 0.60) return ["var(--warning)", "moderate"];
  return ["var(--critical)", "weak"];
}

function card(r, tiers = []) {
  const tier = r.recommended_action || "";
  const label = (tiers.find((t) => t.tier === tier) || {}).label || tier;
  const m = r.match || null;
  const [cColor, cWord] = confidenceWords(r.confidence);

  // An old snapshot has no trace at all -- every read below is guarded, and
  // the absent case renders nothing rather than an empty box.
  const ct = (r.trace || {}).curriculum || {};
  const failed = ct.search_failed === true;
  const skipped = ct.searched === false;

  let cite;
  if (m) {
    cite = `<div class="cite">📎 <code>${esc(m.citation || "")}</code>
       <span class="how">— ${m.content_type === "lab" ? "lab cell" : "slide"},
       ${m.exact_match
          ? `exact match on <code>${esc(m.exact_match)}</code>`
          : `similarity ${esc(m.similarity)}`}</span></div>`;
  } else if (failed) {
    // Three different things can leave a recommendation without a citation.
    // Only ONE of them means "we looked and there is no coverage".
    cite = `<div class="cite failed">
       <b>⚠ CURRICULUM SEARCH FAILED — this is NOT a finding of "no match".</b>
       <div style="margin-top:5px;color:var(--text-secondary)">The search could not run,
       so nothing was learned about existing coverage. Do not read this as a gap in
       the curriculum.</div>
       ${ct.reason ? `<div class="why">${esc(ct.reason)}</div>` : ""}</div>`;
  } else if (skipped) {
    cite = `<div class="cite none">📎 curriculum not searched —
       ${esc(ct.skipped_reason || "below the confidence gate")}</div>`;
  } else {
    // Absence of a citation is information, not an empty field.
    cite = `<div class="cite none">📎 no curriculum match</div>`;
  }

  const ev = r.evidence || [];
  const evHTML = ev.map((e) => `
    <div class="ev-item">
      <span class="ev-src"><b>[${esc(e.tier || "?")}]</b> ${esc(e.source || "?")}</span>
      ${e.note ? ` — ${esc(e.note)}` : ""}
      ${e.url ? `<div class="ev-url">${esc(e.url)}</div>` : ""}
    </div>`).join("") || `<p style="color:var(--text-muted);margin:0">No evidence recorded for this trend.</p>`;

  return `<article class="rec${failed ? " failed" : ""}">
    <div class="rec-top">
      <div class="rec-title">${esc(r.trend || "untitled")}</div>
      <span class="tag" style="background:var(${TIER_VAR[tier] || "--tier-5"});
            color:var(${TIER_VAR[tier] || "--tier-5"}-ink)">${esc(label)}</span>
    </div>
    <div class="rec-meta">
      <span class="pill" style="color:${cColor}">confidence ${
        typeof r.confidence === "number" ? r.confidence.toFixed(2) : "n/a"} · ${cWord}</span>
      ${r.total_score != null ? `<span class="score"><b>${esc(r.total_score)}</b>/5</span>` : ""}
    </div>
    ${cite}
    ${(r.action_plan || []).length
      ? `<ul class="plan">${r.action_plan.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
    <details>
      <summary>Evidence trail (${ev.length} source${ev.length === 1 ? "" : "s"})</summary>
      <div class="ev">
        ${r.verification_note ? `<p class="ev-note">${esc(r.verification_note)}</p>` : ""}
        ${evHTML}
        ${m && m.matched_text
          ? `<div style="margin-top:12px"><b style="font-size:0.75rem;color:var(--text-muted);
             text-transform:uppercase;letter-spacing:0.05em">Matched curriculum text</b>
             <div class="matched">${esc(m.matched_text)}</div></div>` : ""}
      </div>
    </details>
    ${traceBlock(r, tiers)}
  </article>`;
}

// ---------------------------------------------------------------------------
// AGENT TRACE -- rendered INLINE at the bottom of the card, inside a collapsed
// <details>, using the .trace/.tgroup/.tstep components in theme.css.
//
// The card already carries the failure WARNING above, un-collapsed, because
// that must never require a click. This block adds the step-by-step underneath
// it, so the reasoning and the conclusion it produced sit on one surface.
// A failed search opens the block by default -- if the steps explain a wrong
// recommendation, they should not be behind a disclosure.
//
// trace.html is kept as a permalink (one trace, full width, shareable); the
// link moves inside this block rather than standing in for it. A snapshot
// captured before traces existed renders nothing here, as before.
// ---------------------------------------------------------------------------
function traceBlock(r, tiers = []) {
  if (!r.trace) return "";
  const c = r.trace.curriculum || {};
  const v = r.trace.verification || {};
  const cSteps = c.steps || [];
  const vSteps = v.steps || [];
  const n = cSteps.length + ((v.reasoning && v.reasoning.length) || vSteps.length);

  let body = "";
  let notice = "";

  if (c.search_failed) {
    // The reason string is already on the card above, in the un-collapsed
    // warning -- printing it again here would be the same sentence twice on
    // one card. It is repeated only in the case where that warning did NOT
    // render (a match alongside a failed search), which the agents should
    // never produce; the guard is here so the reason can never go missing.
    notice += `<div class="tfail"><b>The curriculum search failed.</b>
      ${r.match && c.reason ? `<div class="tr">${esc(c.reason)}</div>` : ""}</div>`;
  } else if (c.searched === false) {
    notice += `<p class="tnote">The curriculum was never searched &mdash;
      ${esc(c.skipped_reason || "it did not clear the confidence gate.")}</p>`;
  }

  // Newer traces carry the verifier's whole loop (`reasoning`, including steps
  // with no tool call) and which loop ran it (`mode`); older ones only `steps`.
  const vRows = (v.reasoning && v.reasoning.length) ? v.reasoning.map((s, i) => {
    const args = Object.entries(s.tool_args || {})
      .map(([k, val]) => `${esc(k)}=${esc(JSON.stringify(val))}`).join(", ");
    const ask = s.tool ? `Checked <code>${esc(s.tool)}</code>` : esc(s.thought || "");
    const why = s.tool && s.thought
      ? `<div class="tr" style="color:var(--text-muted)">Why: ${esc(s.thought)}</div>` : "";
    return step(i + 1, ask + why, s.observation, args);
  }) : vSteps.map((s, i) => {
    const args = Object.entries(s.arguments || {})
      .map(([k, val]) => `${esc(k)}=${esc(JSON.stringify(val))}`).join(", ");
    return step(i + 1, `Checked <code>${esc(s.tool || "")}</code>`,
                s.result_summary, args);
  });
  const mode = modeText(v.mode);
  body += group("Verification &mdash; is this trend real?", vRows,
                "No verification steps were recorded.", mode);

  body += group("Curriculum &mdash; does it affect what we teach?", cSteps.map((s, i) => {
    const f = Object.entries(s.filters || {})
      .filter(([, val]) => val !== null && val !== undefined && val !== "")
      .map(([k, val]) => `${esc(k)} ${esc(val)}`).join(", ");
    return step(vRows.length + i + 1,
      `Searched for &ldquo;${esc(s.query || "")}&rdquo;${
        f ? ` <span style="color:var(--text-muted)">(${f})</span>` : ""}`,
      s.result_summary, "");
  }), c.search_failed
        ? "The search failed before it issued any query."
        : (c.searched === false ? "Skipped &mdash; see above."
                                : "No searches were issued."));

  if (v.stopped_early || c.stopped_early) {
    body += `<p class="tnote">An agent hit its step limit and was asked to
      conclude early, so this trace may be shorter than the reasoning was.</p>`;
  }

  if (c.searched && !c.search_failed && c.reason) {
    body += `<p class="tgroup" style="margin-top:14px">Conclusion</p>
             <p class="tr" style="margin:0">${esc(c.reason)}</p>`;
  }

  const label = c.search_failed
    ? "Agent trace — why the search failed"
    : `Agent trace (${n} step${n === 1 ? "" : "s"})`;

  return `<details class="rec-trace"${c.search_failed ? " open" : ""}>
    <summary>${esc(label)}</summary>
    <div class="trace">
      ${notice}
      ${flowBlock(r, { tiers, compact: true })}
      <details class="tdetails">
        <summary>Show details</summary>
        ${body}
      </details>
      ${r.index !== undefined
        ? `<a class="tracelink" href="trace.html?i=${r.index}">Open this trace on its own page
           <span class="arrow">→</span></a>` : ""}
    </div>
  </details>`;
}

function modeText(mode) {
  const m = String(mode || "").toLowerCase();
  if (!m) return "";
  if (m.includes("llm loop failed")) return "The model call failed, so the same checks ran from a fixed script instead — scored exactly the same way.";
  if (m.startsWith("deterministic")) return "No model was used: the checks ran from a fixed script. The score comes from what the checks found, as always.";
  if (m.startsWith("agentic")) return "The model chose which checks to run. The score was computed from what those checks found, not by the model.";
  return mode;
}

function group(title, steps, emptyText, note) {
  return `<p class="tgroup">${title}</p>`
    + (note ? `<p class="tnote" style="margin-top:0">${esc(note)}</p>` : "")
    + (steps.length
    ? steps.join("")
    : `<p class="tnote">${emptyText}</p>`);
}

function step(n, ask, got, args) {
  return `<div class="tstep">
    <div class="tn">${n}</div>
    <div>
      <div class="tq">${ask}</div>
      ${args ? `<div class="tr" style="font-family:ui-monospace,Consolas,monospace">${args}</div>` : ""}
      <div class="tr">→ ${esc(got || "")}</div>
    </div>
  </div>`;
}

// ---------------------------------------------------------------------------
// FIVE-NODE FLOW -- Signal -> Verify -> Search curriculum -> Score -> Recommend
// The same picture on the dashboard (compact, inside the trace panel) and on
// the walkthrough (large, revealed in order). Every value is read from the
// recommendation and its trace; nothing is invented, and a snapshot without a
// trace still gets the nodes it can fill.
// ---------------------------------------------------------------------------
function flowBlock(r, opts = {}) {
  const tiers = opts.tiers || [];
  const t = r.trace || {};
  const c = t.curriculum || {};
  const v = t.verification || {};
  const m = r.match || null;

  const tag = String(r.trend || "").split(": ").slice(1).join(": ") || String(r.trend || "");
  const repo = String(r.trend || "").split(": ")[0];

  const vRows = (v.reasoning && v.reasoning.length)
    ? v.reasoning.filter((s) => s.tool).map((s) => ({ tool: s.tool, args: s.tool_args || {}, out: s.observation || "" }))
    : (v.steps || []).map((s) => ({ tool: s.tool, args: s.arguments || {}, out: s.result_summary || "" }));
  const outcome = (text) => /confirmed|matched\b/i.test(text) ? "ok"
    : /not found|could not|failed|no repository|no matching/i.test(text) ? "miss" : "info";
  const confirmed = /CONFIRMED/.test(r.verification_note || "") || vRows.some((x) => /CONFIRMED/.test(x.out));
  const mode = String(v.mode || "").toLowerCase();
  const modeBadge = !mode ? "" : mode.includes("llm loop failed") ? "scripted · model failed"
    : mode.startsWith("deterministic") ? "scripted" : mode.startsWith("agentic") ? "agentic" : "";

  const hits = (s) => { const k = /^(\d+) hit/.exec(s || ""); return k ? +k[1] : null; };
  const cRows = (c.steps || []).map((s) => ({
    q: s.query || "", out: s.result_summary || "",
    state: /exact[:\s]/i.test(s.result_summary || "") || hits(s.result_summary) > 0 ? "ok"
      : hits(s.result_summary) === 0 || /^no results/i.test(s.result_summary || "") ? "miss" : "info" }));

  const where = m ? String(m.citation || "").split(" / ").pop() : "";
  const search = c.search_failed ? { v: "search FAILED", s: "bad" }
    : c.searched === false ? { v: "not searched", s: "muted" }
    : m ? { v: `matched ${where}`, s: "ok" } : { v: "no match", s: "muted" };
  const label = (tiers.find((x) => x.tier === r.recommended_action) || {}).label
    || String(r.recommended_action || "").replace(/_/g, " ");

  const chip = (text, state, title) => `<span class="fchip ${state}" title="${esc(title || "")}">${
    state === "ok" ? "✓" : state === "miss" ? "✗" : "·"} ${esc(text)}</span>`;
  // chip text: the tool plus the part of its argument a viewer cares about
  // ("verify_release 1.6.4", "github_lookup langchain"); the full call and its
  // result stay on hover
  const short = (tool, o) => {
    const val = String((tool === "verify_release" ? o.version : o.query || o.repo) || Object.values(o)[0] || "");
    return val.split(/==|\//).filter(Boolean).pop() || val;
  };

  const nodes = [
    { k: "Signal", v: tag, sub: repo, s: "info" },
    { k: "Verify", v: confirmed ? "release confirmed" : `confidence ${Number(r.confidence).toFixed(2)}`,
      s: confirmed ? "ok" : "info", badge: modeBadge,
      chips: vRows.map((x) => chip(`${x.tool} ${short(x.tool, x.args)}`, outcome(x.out),
             `${x.tool}(${JSON.stringify(x.args)}) -> ${x.out}`)) },
    { k: "Search curriculum", v: search.v, s: search.s,
      chips: cRows.map((x) => chip(`"${x.q}"`, x.state, x.out)) },
    { k: "Score", v: r.total_score != null ? `${r.total_score} / 5` : "—", s: "info" },
    { k: "Recommend", v: label, s: r.recommended_action === "watch" ? "muted" : "ok" },
  ];

  return `<div class="flow5${opts.compact ? " compact" : ""}${opts.animate ? " animate" : ""}" role="list"
      aria-label="Pipeline for this recommendation">${nodes.map((nd, i) => `${
      i ? `<div class="farrow" aria-hidden="true" style="--i:${i - 0.5}">→</div>` : ""}
    <div class="fnode ${nd.s}" role="listitem" style="--i:${i}">
      <div class="fk">${esc(nd.k)}${nd.badge ? ` <span class="fbadge">${esc(nd.badge)}</span>` : ""}</div>
      <div class="fv">${nd.s === "ok" ? "✓ " : nd.s === "bad" ? "✗ " : ""}${esc(nd.v)}</div>
      ${nd.sub ? `<div class="fsub">${esc(nd.sub)}</div>` : ""}
      ${nd.chips && nd.chips.length ? `<div class="fchips">${nd.chips.join("")}</div>` : ""}
    </div>`).join("")}
  </div>`;
}

// ---------------------------------------------------------------------------
// HANDOFF -- the curriculum agent's conclusion beside the plan's first step,
// joined by "lost in the handoff". Both texts come from the recommendation
// itself; "" when either is missing. Used by walkthrough.html (step 3) and
// by C-Sync, so the picture is drawn from one copy.
// ---------------------------------------------------------------------------
function handoffBlock(r) {
  const concl = ((r.trace || {}).curriculum || {}).reason || "";
  const plan0 = (r.action_plan || [])[0] || "";
  if (!concl || !plan0) return "";
  const clip = (s, n) => { s = String(s).replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s; };
  const mark = (t, re) => esc(t).replace(re, (m) => `<span class="hl">${m}</span>`);
  return `<div class="handoff">
        <div class="bubble ok"><div class="who">Curriculum agent concluded</div>
          ${mark(clip(concl, 170), /deprecat\w*/gi)}</div>
        <div class="hand-arrow"><svg viewBox="0 0 150 44" aria-hidden="true">
            <line x1="6" y1="22" x2="132" y2="22" stroke="currentColor" stroke-width="3"/>
            <path d="M 130 12 L 146 22 L 130 32 Z" fill="currentColor"/></svg>
          <div class="lbl">lost in the handoff</div></div>
        <div class="bubble bad"><div class="who">Plan, first step</div>
          ${mark(clip(plan0, 150), /import[^.]*?path|module path/gi)}</div>
      </div>`;
}
