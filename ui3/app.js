/*
  UI3 -- one panel per agent, each with a chart drawn from the recorded run.

  DATA RULE: every number on this page comes from /summary, /recommendations,
  /tiers or /signals. Nothing is simulated or padded. Where a value is DERIVED
  (e.g. maturity/relevance split out of total_score) the panel says how, using
  the same bands the agents use, so the chart cannot claim more than the data.

  COLOR: tiers are ORDINAL and reuse theme.css --tier-N (the same blue ramp as
  the advanced dashboard). Monitoring sources are categorical: slots 1-3 of the
  reference palette, validated light + dark (aqua is <3:1 on light, so every
  source also has a direct text label and a data table).
*/

// Mirrors schemas.py / agents -- used only to LABEL charts, never to re-decide.
const MATURE_FLOOR = 4;              // recommendation.py
const CURRICULUM_GATE = 0.4;         // recommendation.py: confidence >= 0.4 gets searched
const RELEVANCE_BANDS = [0.48, 0.55, 0.65];   // schemas.RELEVANCE_FLOOR, evaluation.py
const MATURITY_BANDS = [0.3, 0.5, 0.7, 0.85]; // evaluation._maturity_score

const SOURCES = [
    { key: 'github', label: 'GitHub releases', cls: 's1' },
    { key: 'openai_blog', label: 'OpenAI blog', cls: 's2' },
    { key: 'langchain_blog', label: 'LangChain blog', cls: 's3' }
];

// Sequential blue ramp (reference palette steps 150->700) with computed inks.
// On a dark surface "more" must mean MORE contrast, so the ramp runs the other way.
const SEQ_LIGHT = ['#b7d3f6', '#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#0d366b'];
const SEQ_LIGHT_INK = ['#0b0b0b', '#0b0b0b', '#0b0b0b', '#0b0b0b', '#ffffff', '#ffffff'];
const isDark = () => {
    const t = document.documentElement.dataset.theme;
    return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
};
let SEQ = SEQ_LIGHT, SEQ_INK = SEQ_LIGHT_INK;
function pickRamp() {
    SEQ = isDark() ? [...SEQ_LIGHT].reverse() : SEQ_LIGHT;
    SEQ_INK = isDark() ? [...SEQ_LIGHT_INK].reverse() : SEQ_LIGHT_INK;
}

let TIER_ORDER = ['update_existing_material', 'add_new_lesson', 'add_optional_content',
    'investigate_larger_change', 'watch'];
let TIER_LABEL = {};

const state = { filter: 'all', summary: null, recommendations: [], signals: null };

const $ = (id) => document.getElementById(id);
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

$('refreshBtn').addEventListener('click', loadDashboard);
$('replayBtn').addEventListener('click', replayAll);

document.querySelectorAll('.filter-button').forEach((button) => {
    button.addEventListener('click', () => {
        state.filter = button.dataset.filter;
        document.querySelectorAll('.filter-button').forEach((b) => b.classList.toggle('active', b === button));
        renderRecommendations();
    });
});

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Request failed for ${url}: ${response.status} ${response.statusText}`);
    return response.json();
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function formatDate(value) {
    if (!value) return 'Unknown';
    const d = new Date(value);
    return isNaN(d) ? value : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

const shortDay = (d) => d.toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' });

function tierIndex(tier) {
    const i = TIER_ORDER.indexOf(tier);
    return i < 0 ? TIER_ORDER.length : i + 1;
}
const tierFill = (tier) => `var(--tier-${Math.min(tierIndex(tier), 5)})`;
const tierInk = (tier) => `var(--tier-${Math.min(tierIndex(tier), 5)}-ink)`;
function tierLabel(tier) {
    const raw = TIER_LABEL[tier] || tier || 'unknown';
    return raw.charAt(0) + raw.slice(1).toLowerCase().replace(/_/g, ' ');
}

function shortTrend(title, n = 46) {
    const t = String(title || '').replace(/^[\w.-]+\/[\w.-]+:\s*/, '');
    return t.length > n ? t.slice(0, n - 1) + '…' : t;
}

// Same bands as evaluation._maturity_score.
function maturityOf(conf) {
    const c = Number(conf) || 0;
    if (c >= 0.85) return 5;
    if (c >= 0.70) return 4;
    if (c >= 0.50) return 3;
    if (c >= 0.30) return 2;
    return 1;
}
// total = 0.5*maturity + 0.5*relevance (schemas weights) => relevance = 2*total - maturity.
function relevanceOf(rec) {
    const r = Math.round(2 * Number(rec.total_score || 0) - maturityOf(rec.confidence));
    return Math.max(1, Math.min(5, r));
}

// Tooltips: content is kept in an array and referenced by index, so no HTML
// ever travels through an attribute.
const tips = [];
function tip(html) { tips.push(html); return `data-tip="${tips.length - 1}" tabindex="0"`; }

function dataTable(caption, cols, rows) {
    return `
      <details class="data-table">
        <summary>Show data table</summary>
        <table>
          <caption>${escapeHtml(caption)}</caption>
          <thead><tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
          <tbody>${rows.map((r) => `<tr>${r.map((v) => `<td>${escapeHtml(v)}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
      </details>`;
}

// ---------------------------------------------------------------------------
// hero + flow
// ---------------------------------------------------------------------------

function countUp(el, target) {
    const n = Number(target);
    if (!Number.isFinite(n) || reduceMotion) { el.textContent = target; return; }
    const start = performance.now();
    const dur = 900;
    const step = (now) => {
        const p = Math.min((now - start) / dur, 1);
        el.textContent = Math.round(n * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

function renderSummaryCards(summary) {
    const f = summary.funnel || {};
    const cards = [
        { label: 'Signals collected', value: f.signals ?? '—' },
        { label: 'Trend clusters', value: f.clusters ?? '—' },
        { label: 'Recommendations', value: f.recommendations ?? state.recommendations.length },
        { label: 'Actionable', value: summary.actionable ?? '—' }
    ];
    $('summaryGrid').innerHTML = cards.map((c) => `
        <div class="summary-card">
          <span class="label">${c.label}</span>
          <span class="value" data-count="${escapeHtml(c.value)}">${escapeHtml(c.value)}</span>
        </div>`).join('');
    $('summaryGrid').querySelectorAll('[data-count]').forEach((el) => countUp(el, el.dataset.count));
}

function agentStats() {
    const f = state.summary.funnel || {};
    const recs = state.recommendations;
    const matched = recs.filter((r) => r.match).length;
    return [
        { key: 'monitoring', name: 'Monitoring', value: f.signals, unit: 'signals' },
        { key: 'clustering', name: 'Clustering', value: f.clusters, unit: 'clusters' },
        { key: 'verification', name: 'Verification', value: f.evaluated, unit: 'verified' },
        { key: 'curriculum', name: 'Curriculum', value: matched, unit: 'matched' },
        { key: 'evaluation', name: 'Evaluation', value: recs.length, unit: 'scored' },
        { key: 'recommendation', name: 'Recommendation', value: state.summary.actionable, unit: 'actionable' }
    ];
}

function renderFlow() {
    const stats = agentStats();
    $('pipelineFlow').innerHTML = stats.map((s, i) => `
        ${i ? '<div class="flow-link" aria-hidden="true"><span></span><span></span><span></span></div>' : ''}
        <a class="flow-node" role="listitem" href="#agent-${s.key}" style="--i:${i}">
          <span class="flow-step">${i + 1}</span>
          <span class="flow-name">${s.name}</span>
          <span class="flow-value">${escapeHtml(s.value ?? '—')}</span>
          <span class="flow-unit">${s.unit}</span>
        </a>`).join('');
}

// ---------------------------------------------------------------------------
// agent panels
// ---------------------------------------------------------------------------

function panel({ key, step, name, role, purpose, headline, body, foot }) {
    return `
      <section class="panel agent-panel" id="agent-${key}">
        <div class="agent-head">
          <span class="agent-step">${step}</span>
          <div class="agent-title">
            <p class="eyebrow">${role}</p>
            <h3 class="agent-name">${name} agent</h3>
          </div>
          <div class="agent-headline">${headline}</div>
        </div>
        <p class="agent-purpose">${purpose}</p>
        <div class="agent-body">${body}</div>
        ${foot ? `<p class="agent-foot">${foot}</p>` : ''}
      </section>`;
}

// 1. MONITORING -- stacked daily columns by source
function monitoringChart() {
    const sig = state.signals?.signals || [];
    if (!sig.length) return '<div class="empty-state">Signal file not available from /signals.</div>';

    const dayKey = (s) => (s.published || '').slice(0, 10);
    const days = sig.map(dayKey).filter(Boolean).sort();
    const first = new Date(days[0] + 'T00:00:00Z');
    const last = new Date(days[days.length - 1] + 'T00:00:00Z');
    const nDays = Math.round((last - first) / 864e5) + 1;

    const grid = [];
    for (let d = 0; d < nDays; d++) {
        const date = new Date(first.getTime() + d * 864e5);
        grid.push({ date, key: date.toISOString().slice(0, 10), bySource: {} });
    }
    const idx = Object.fromEntries(grid.map((g, i) => [g.key, i]));
    sig.forEach((s) => {
        const g = grid[idx[dayKey(s)]];
        if (!g) return;
        (g.bySource[s.source] ||= []).push(s.title);
    });

    const maxDay = Math.max(...grid.map((g) => Object.values(g.bySource).reduce((a, b) => a + b.length, 0)), 1);
    const yMax = Math.ceil(maxDay / 2) * 2;
    const W = 720, H = 230, L = 30, R = 8, T = 12, B = 30;
    const pw = W - L - R, ph = H - T - B;
    const slot = pw / nDays;
    const bw = Math.max(Math.min(slot - 4, 22), 3);
    const y = (v) => T + ph - (v / yMax) * ph;

    let bars = '';
    grid.forEach((g, i) => {
        let acc = 0;
        let segs = '';
        SOURCES.forEach((src) => {
            const titles = g.bySource[src.key] || [];
            if (!titles.length) return;
            const y0 = y(acc), y1 = y(acc + titles.length);
            const hgt = Math.max(y0 - y1 - 2, 1);   // 2px surface gap between stacked fills
            segs += `<rect class="${src.cls}" x="${(L + i * slot + (slot - bw) / 2).toFixed(1)}" y="${y1.toFixed(1)}"
                width="${bw.toFixed(1)}" height="${hgt.toFixed(1)}" rx="2"
                ${tip(`<strong>${shortDay(g.date)} · ${src.label}</strong><br>${titles.length} signal${titles.length > 1 ? 's' : ''}<ul>${titles.slice(0, 4).map((t) => `<li>${escapeHtml(shortTrend(t, 60))}</li>`).join('')}${titles.length > 4 ? `<li>+${titles.length - 4} more</li>` : ''}</ul>`)}></rect>`;
            acc += titles.length;
        });
        if (segs) bars += `<g class="grow" style="--d:${i * 28}ms">${segs}</g>`;
    });

    let axis = '';
    for (let v = 0; v <= yMax; v += Math.max(1, yMax / 4)) {
        axis += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"></line>
                 <text class="tick" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
    }
    const every = Math.ceil(nDays / 7);
    grid.forEach((g, i) => {
        if (i % every === 0) axis += `<text class="tick" x="${L + i * slot + slot / 2}" y="${H - 10}" text-anchor="middle">${shortDay(g.date)}</text>`;
    });

    const totals = SOURCES.map((s) => ({ ...s, n: sig.filter((x) => x.source === s.key).length }));
    const legend = totals.map((s) => `
        <span class="legend-item"><span class="legend-swatch ${s.cls}"></span>${s.label} <strong>${s.n}</strong></span>`).join('');

    const tableRows = grid.filter((g) => Object.keys(g.bySource).length)
        .map((g) => [g.key, ...SOURCES.map((s) => (g.bySource[s.key] || []).length)]);

    return `
      <div class="chart-legend">${legend}</div>
      <svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Signals collected per day, stacked by source">
        ${axis}<line class="baseline" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"></line>${bars}
      </svg>
      ${dataTable('Signals per day by source', ['Day', ...SOURCES.map((s) => s.label)], tableRows)}`;
}

// 2. CLUSTERING -- dots that physically merge (FLIP animation)
function clusteringChart() {
    const data = state.signals;
    if (!data?.clusters?.length) return '<div class="empty-state">Cluster data not available from /signals.</div>';
    const merged = data.clusters.filter((c) => c.members.length > 1);
    const list = merged.map((c) => `
        <li class="merge-item">
          <span class="merge-count">${c.members.length} → 1</span>
          <div>${c.members.map((m) => `<div class="merge-title"><span class="legend-swatch ${srcCls(data.signals[m].source)}"></span>${escapeHtml(shortTrend(data.signals[m].title, 70))}</div>`).join('')}</div>
        </li>`).join('');
    const warn = data.clusters_match_snapshot ? '' :
        `<p class="warn-line">Re-running clustering today gives ${data.clusters.length} clusters, but the snapshot recorded ${state.summary.funnel?.clusters}. Clustering code has changed since the capture.</p>`;

    return `
      <div class="cluster-top">
        <div class="cluster-counter"><span id="clusterCount">${data.signals.length}</span> <span id="clusterUnit">separate signals</span></div>
        <button type="button" class="ghost small-btn" id="clusterReplay">Replay merge</button>
      </div>
      <div class="cluster-stage" id="clusterStage" aria-label="Each dot is a signal; merged dots are signals grouped into one trend"></div>
      <div class="chart-legend">${SOURCES.map((s) => `<span class="legend-item"><span class="legend-swatch ${s.cls}"></span>${s.label}</span>`).join('')}
        <span class="legend-item"><span class="legend-ring"></span>merged into one trend</span></div>
      ${warn}
      <h5 class="sub-head">The ${merged.length} merges it made</h5>
      <ul class="merge-list">${list || '<li class="muted">No signals were merged in this run.</li>'}</ul>`;
}

const srcCls = (key) => (SOURCES.find((s) => s.key === key) || { cls: 's0' }).cls;

let clusterTimer = null;
function playClustering() {
    const stage = $('clusterStage');
    const data = state.signals;
    if (!stage || !data?.clusters?.length) return;
    clearTimeout(clusterTimer);

    const dots = data.signals.map((s, i) => {
        const el = document.createElement('span');
        el.className = `cdot ${srcCls(s.source)}`;
        el.dataset.tip = tips.push(`<strong>${escapeHtml(shortTrend(s.title, 70))}</strong><br>${escapeHtml(s.source)} · ${escapeHtml((s.published || '').slice(0, 10))}`) - 1;
        el.tabIndex = 0;
        el.dataset.i = i;
        return el;
    });

    // Layout A: every signal on its own.
    stage.innerHTML = '';
    stage.classList.remove('merged');
    dots.forEach((d) => {
        const cell = document.createElement('span');
        cell.className = 'ccell';
        cell.appendChild(d);
        stage.appendChild(cell);
    });
    $('clusterCount').textContent = data.signals.length;
    $('clusterUnit').textContent = 'separate signals';

    const toB = () => {
        const first = new Map(dots.map((d) => [d, d.getBoundingClientRect()]));
        stage.innerHTML = '';
        data.clusters.forEach((c) => {
            const cell = document.createElement('span');
            cell.className = 'ccell' + (c.members.length > 1 ? ' is-merged' : '');
            c.members.forEach((m) => cell.appendChild(dots[m]));
            stage.appendChild(cell);
        });
        stage.classList.add('merged');
        dots.forEach((d, i) => {
            const a = first.get(d), b = d.getBoundingClientRect();
            const dx = a.left - b.left, dy = a.top - b.top;
            if (!dx && !dy) return;
            d.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }],
                { duration: 900, delay: i * 8, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'backwards' });
        });
        $('clusterCount').textContent = data.clusters.length;
        $('clusterUnit').textContent = 'trend clusters';
    };
    if (reduceMotion) toB(); else clusterTimer = setTimeout(toB, 900);
}

// 3. VERIFICATION -- confidence strip with maturity bands and gates
function verificationChart() {
    const recs = state.recommendations;
    // Height follows the tallest stack of identical confidences, so dots never
    // climb into the band labels.
    const tallest = Math.max(1, ...Object.values(recs.reduce((m, r) => {
        const k = (Number(r.confidence) || 0).toFixed(2);
        m[k] = (m[k] || 0) + 1;
        return m;
    }, {})));
    const base = 52 + tallest * 17;
    const W = 720, H = base + 50, L = 16, R = 16;
    const pw = W - L - R;
    const x = (c) => L + c * pw;
    const edges = [0, ...MATURITY_BANDS, 1];

    let bands = '';
    for (let i = 0; i < 5; i++) {
        bands += `<rect class="band band-${i}" x="${x(edges[i])}" y="18" width="${x(edges[i + 1]) - x(edges[i])}" height="${base - 18}"></rect>
                  <text class="band-label" x="${(x(edges[i]) + x(edges[i + 1])) / 2}" y="32" text-anchor="middle">maturity ${i + 1}</text>`;
    }
    const stacks = {};
    const dots = recs.map((r, i) => {
        const c = Number(r.confidence) || 0;
        const k = (stacks[c.toFixed(2)] = (stacks[c.toFixed(2)] ?? -1) + 1);
        const ev = Array.isArray(r.evidence) ? r.evidence : [];
        const prim = ev.filter((e) => e.tier === 'primary').length;
        return `<circle class="vdot drop" cx="${x(c)}" cy="${base - 10 - k * 17}" r="7" style="--d:${i * 60}ms"
            ${tip(`<strong>${escapeHtml(shortTrend(r.trend, 60))}</strong><br>confidence ${c.toFixed(2)} → maturity ${maturityOf(c)}/5<br>${ev.length} evidence item${ev.length === 1 ? '' : 's'} (${prim} primary)<br><span class="tip-muted">${escapeHtml(r.verification_note || '')}</span>`)}></circle>`;
    }).join('');

    const gate = (v, label, cls) => `
        <line class="gate ${cls}" x1="${x(v)}" x2="${x(v)}" y1="14" y2="${base + 6}"></line>
        <text class="gate-label" x="${x(v) + 4}" y="${base + 22}">${label}</text>`;
    let ticks = '';
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((v) => { ticks += `<text class="tick" x="${x(v)}" y="${H - 4}" text-anchor="middle">${v.toFixed(1)}</text>`; });

    const low = recs.filter((r) => maturityOf(r.confidence) < MATURE_FLOOR).length;
    const evTotal = recs.reduce((a, r) => a + (r.evidence?.length || 0), 0);
    const evPrimary = recs.reduce((a, r) => a + (r.evidence || []).filter((e) => e.tier === 'primary').length, 0);

    return `
      <div class="mini-stats">
        <div><strong>${recs.length - low}</strong><span>solid enough to act on</span></div>
        <div><strong>${low}</strong><span>too thin — held at watch</span></div>
        <div><strong>${evPrimary}/${evTotal}</strong><span>evidence items from primary sources</span></div>
      </div>
      <svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Verification confidence per trend">
        ${bands}
        <line class="baseline" x1="${L}" x2="${W - R}" y1="${base}" y2="${base}"></line>
        ${gate(CURRICULUM_GATE, 'curriculum search gate (≥ 0.40)', 'gate-a')}
        ${gate(0.7, `act-on floor (maturity ≥ ${MATURE_FLOOR})`, 'gate-b')}
        ${dots}${ticks}
      </svg>
      ${dataTable('Verification confidence per trend', ['Trend', 'Confidence', 'Maturity', 'Evidence'],
        recs.map((r) => [shortTrend(r.trend, 60), Number(r.confidence).toFixed(2), maturityOf(r.confidence), r.evidence?.length || 0]))}`;
}

// 4. CURRICULUM -- week x type heatmap + similarity bars against relevance bands
function curriculumChart() {
    const recs = state.recommendations;
    const matched = recs.filter((r) => r.match);
    const searched = recs.filter((r) => Number(r.confidence) >= CURRICULUM_GATE);
    const withTrace = recs.filter((r) => r.trace?.curriculum);
    const failed = withTrace.filter((r) => r.trace.curriculum.search_failed).length;

    const weeks = [2, 3, 4, 5, 6];
    const types = [['lab', 'Lab notebooks'], ['slides', 'Slides']];
    const count = (w, t) => matched.filter((r) => r.match.week === w && r.match.content_type === t);
    const maxC = Math.max(1, ...weeks.flatMap((w) => types.map(([t]) => count(w, t).length)));

    const heat = `
      <div class="heat" style="--cols:${weeks.length}">
        <span></span>${weeks.map((w) => `<span class="heat-col">Week ${w}</span>`).join('')}
        ${types.map(([t, label]) => `
          <span class="heat-row">${label}</span>
          ${weeks.map((w, wi) => {
              const hits = count(w, t);
              const n = hits.length;
              const step = n ? Math.min(SEQ.length - 1, Math.round(((n / maxC) * (SEQ.length - 2))) + 1) : -1;
              const style = n ? `background:${SEQ[step]};color:${SEQ_INK[step]}` : '';
              return `<span class="heat-cell pop ${n ? '' : 'empty'}" style="${style};--d:${wi * 70}ms"
                  ${tip(n ? `<strong>Week ${w} · ${label}</strong><ul>${hits.map((r) => `<li>${escapeHtml(r.match.citation || shortTrend(r.trend))}</li>`).join('')}</ul>` : `<strong>Week ${w} · ${label}</strong><br>no trend touched this material`)}>${n || ''}</span>`;
          }).join('')}`).join('')}
      </div>`;

    const bars = matched.slice().sort((a, b) => (b.match.exact_match ? 2 : b.match.similarity || 0) - (a.match.exact_match ? 2 : a.match.similarity || 0))
        .map((r, i) => {
            const m = r.match;
            const exact = !!m.exact_match;
            const sim = exact ? 1 : Number(m.similarity || 0);
            return `
              <div class="sim-row" ${tip(`<strong>${escapeHtml(shortTrend(r.trend, 60))}</strong><br>${escapeHtml(m.citation || '')}<br>${exact ? `exact identifier match: <code>${escapeHtml(m.exact_match)}</code> → relevance 5` : `similarity ${sim.toFixed(3)} → relevance ${relevanceOf(r)}`}`)}>
                <span class="sim-label">${escapeHtml(shortTrend(r.trend, 34))}</span>
                <span class="sim-track">
                  ${RELEVANCE_BANDS.map((b) => `<i class="sim-tick" style="left:${b * 100}%"></i>`).join('')}
                  <span class="sim-fill ${exact ? 'exact' : ''}" style="--w:${sim * 100}%;--d:${i * 90}ms"></span>
                </span>
                <span class="sim-value">${exact ? `exact: ${escapeHtml(m.exact_match)}` : sim.toFixed(2)}</span>
              </div>`;
        }).join('');

    const failNote = withTrace.length
        ? (failed ? `<p class="warn-line">${failed} search${failed > 1 ? 'es' : ''} FAILED to run — that is not a finding of "no match".</p>` : '')
        : '<p class="agent-foot">This snapshot carries no agent traces, so a failed search cannot be told apart from a genuine no-match here. Re-capture to record them.</p>';

    return `
      <div class="mini-stats">
        <div><strong>${searched.length}</strong><span>trends searched against the course</span></div>
        <div><strong>${matched.length}</strong><span>found material they touch</span></div>
        <div><strong>${searched.length - matched.length}</strong><span>no existing coverage found</span></div>
      </div>
      <div class="two-col">
        <div>
          <h5 class="sub-head">Where the matches landed</h5>
          ${heat}
        </div>
        <div>
          <h5 class="sub-head">How close each match is</h5>
          <div class="sim-scale"><span>0</span><span class="sim-band-note">ticks: relevance 3 · 4 · 5</span><span>1</span></div>
          ${bars || '<div class="empty-state">No curriculum matches.</div>'}
        </div>
      </div>
      ${failNote}
      ${dataTable('Curriculum matches', ['Trend', 'Citation', 'Similarity', 'Exact identifier'],
        matched.map((r) => [shortTrend(r.trend, 50), r.match.citation || '', r.match.similarity ?? '', r.match.exact_match || '']))}`;
}

// 5. EVALUATION -- maturity x relevance scoring grid
function evaluationChart() {
    const recs = state.recommendations;
    const cell = {};
    recs.forEach((r) => { (cell[`${maturityOf(r.confidence)}-${relevanceOf(r)}`] ||= []).push(r); });

    let grid = '';
    for (let rel = 5; rel >= 1; rel--) {
        grid += `<span class="mx-axis-y">${rel}</span>`;
        for (let mat = 1; mat <= 5; mat++) {
            const hits = cell[`${mat}-${rel}`] || [];
            const total = (mat + rel) / 2;
            const step = Math.round(((total - 1) / 4) * (SEQ.length - 1));
            grid += `<span class="mx-cell pop ${hits.length ? 'has' : ''} ${mat < MATURE_FLOOR ? 'below-floor' : ''}"
                style="background:${SEQ[step]};color:${SEQ_INK[step]};--d:${(mat + (5 - rel)) * 45}ms"
                ${tip(`<strong>maturity ${mat} · relevance ${rel} → total ${total.toFixed(1)}</strong>${hits.length ? `<ul>${hits.map((r) => `<li>${escapeHtml(shortTrend(r.trend, 56))}</li>`).join('')}</ul>` : '<br>no trends here'}`)}>
                ${hits.length ? `<b>${hits.length}</b>` : ''}</span>`;
        }
    }
    grid += `<span></span>${[1, 2, 3, 4, 5].map((m) => `<span class="mx-axis-x">${m}</span>`).join('')}`;

    const scores = recs.map((r) => Number(r.total_score || 0));
    const avg = scores.reduce((a, b) => a + b, 0) / (scores.length || 1);

    return `
      <div class="two-col mx-wrap">
        <div>
          <div class="mx-y-title">Relevance (from curriculum match)</div>
          <div class="matrix">${grid}</div>
          <div class="mx-x-title">Maturity (from verification confidence)</div>
        </div>
        <div class="mx-side">
          <div class="big-number">${avg.toFixed(1)}<span>/ 5</span></div>
          <p class="muted small">average total score across ${recs.length} trends</p>
          <p class="formula">total = ½ × maturity + ½ × relevance</p>
          <p class="muted small">Cell shade is the total score. Numbers are how many trends landed in that cell.
             Columns left of maturity ${MATURE_FLOOR} are hatched: those trends are never acted on, whatever their relevance.</p>
          <p class="muted small">Python computes both scores from facts; the model only writes the explanation.
             Maturity and relevance are split back out of <code>total_score</code> here using the agent's own bands.</p>
        </div>
      </div>
      ${dataTable('Evaluation scores', ['Trend', 'Maturity', 'Relevance', 'Total'],
        recs.map((r) => [shortTrend(r.trend, 56), maturityOf(r.confidence), relevanceOf(r), Number(r.total_score).toFixed(1)]))}`;
}

// 6. RECOMMENDATION -- gate flow (sankey) from evaluated -> route -> tier
function recommendationChart() {
    const recs = state.recommendations;
    const routeOf = (r) => maturityOf(r.confidence) < MATURE_FLOOR ? 'immature' : (r.match ? 'matched' : 'unmatched');
    const ROUTES = [
        { key: 'matched', label: 'Existing material found' },
        { key: 'unmatched', label: 'No existing material' },
        { key: 'immature', label: `Too early (maturity < ${MATURE_FLOOR})` }
    ].filter((rt) => recs.some((r) => routeOf(r) === rt.key));
    const tiers = TIER_ORDER.filter((t) => recs.some((r) => r.recommended_action === t));

    const W = 720, H = 300, NW = 12, GAP = 14, T = 10;
    const unit = (H - T * 2 - GAP * (Math.max(ROUTES.length, tiers.length) - 1)) / recs.length;
    const X = [110, 320, 520];

    const layout = (items, countFn) => {
        const total = items.reduce((a, it) => a + countFn(it) * unit, 0) + GAP * (items.length - 1);
        let y = (H - total) / 2;
        return Object.fromEntries(items.map((it) => {
            const h = countFn(it) * unit;
            const out = [it.key || it, { y, h, inOff: 0, outOff: 0 }];
            y += h + GAP;
            return out;
        }));
    };
    const src = { root: { y: (H - recs.length * unit) / 2, h: recs.length * unit, inOff: 0, outOff: 0 } };
    const rNodes = layout(ROUTES, (rt) => recs.filter((r) => routeOf(r) === rt.key).length);
    const tNodes = layout(tiers, (t) => recs.filter((r) => r.recommended_action === t).length);

    const link = (a, b, x0, x1, n, color, delay, tipHtml) => {
        const w = n * unit;
        const y0 = a.y + a.outOff + w / 2, y1 = b.y + b.inOff + w / 2;
        a.outOff += w; b.inOff += w;
        const mx = (x0 + x1) / 2;
        return `<path class="flow-path draw" d="M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}"
            stroke="${color}" stroke-width="${Math.max(w - 2, 1)}" pathLength="1" style="--d:${delay}ms" ${tip(tipHtml)}></path>`;
    };

    let links = '';
    ROUTES.forEach((rt, i) => {
        const n = recs.filter((r) => routeOf(r) === rt.key).length;
        links += link(src.root, rNodes[rt.key], X[0] + NW, X[1], n, 'var(--flow-neutral)', i * 120,
            `<strong>${rt.label}</strong><br>${n} of ${recs.length} trends`);
    });
    ROUTES.forEach((rt, i) => {
        tiers.forEach((t, j) => {
            const group = recs.filter((r) => routeOf(r) === rt.key && r.recommended_action === t);
            if (!group.length) return;
            links += link(rNodes[rt.key], tNodes[t], X[1] + NW, X[2], group.length, tierFill(t), 400 + (i * 3 + j) * 110,
                `<strong>${rt.label} → ${tierLabel(t)}</strong><ul>${group.map((r) => `<li>${escapeHtml(shortTrend(r.trend, 56))}</li>`).join('')}</ul>`);
        });
    });

    // pos: 'left' / 'right' of the node, or 'mid' -- route nodes sit between two sets of
    // bands, so their label goes on a surface-coloured chip centred over the node.
    const node = (x, n, fill, label, count, pos) => {
        const rect = `<rect class="flow-node-rect" x="${x}" y="${n.y}" width="${NW}" height="${Math.max(n.h, 2)}" rx="3" fill="${fill}"></rect>`;
        const cy = n.y + n.h / 2;
        if (pos === 'mid') {
            return `${rect}<text class="node-label chip" x="${x + NW / 2}" y="${cy + 4}" text-anchor="middle">${escapeHtml(label)} · ${count}</text>`;
        }
        const tx = pos === 'left' ? x - 8 : x + NW + 8;
        const anchor = pos === 'left' ? 'end' : 'start';
        return `${rect}
            <text class="node-label" x="${tx}" y="${cy - 2}" text-anchor="${anchor}">${escapeHtml(label)}</text>
            <text class="node-count" x="${tx}" y="${cy + 13}" text-anchor="${anchor}">${count}</text>`;
    };

    let nodes = node(X[0], src.root, 'var(--text-secondary)', 'Scored trends', recs.length, 'left');
    ROUTES.forEach((rt) => { nodes += node(X[1], rNodes[rt.key], 'var(--text-muted)', rt.label, recs.filter((r) => routeOf(r) === rt.key).length, 'mid'); });
    tiers.forEach((t) => { nodes += node(X[2], tNodes[t], tierFill(t), tierLabel(t), recs.filter((r) => r.recommended_action === t).length, 'right'); });

    const gates = `
      <ol class="gate-list">
        <li><b>Maturity gate.</b> Maturity below ${MATURE_FLOOR} → <em>watch</em>. Not established enough to act on.</li>
        <li><b>Coverage found.</b> Relevance ≥ 4 → <em>update existing material</em>; weaker → <em>add optional content</em>.</li>
        <li><b>No coverage.</b> A plain version bump, or a title outside the course's domain → <em>watch</em>. Only a new, in-domain capability becomes <em>add new lesson</em>.</li>
        <li><b>Never reached:</b> <em>investigate larger change</em> — needs a multi-module signal the pipeline does not produce yet.</li>
      </ol>`;

    return `
      <svg class="chart sankey" viewBox="0 0 ${W} ${H}" role="img" aria-label="How scored trends flow through the tier gates">
        ${links}${nodes}
      </svg>
      ${gates}
      ${dataTable('Tier routing', ['Trend', 'Route', 'Tier'],
        recs.map((r) => [shortTrend(r.trend, 56), (ROUTES.find((rt) => rt.key === routeOf(r)) || {}).label, tierLabel(r.recommended_action)]))}`;
}

function renderAgents() {
    tips.length = 0;
    const s = state.summary;
    const f = s.funnel || {};
    const recs = state.recommendations;
    const sig = state.signals?.signals || [];
    const merges = (state.signals?.clusters || []).filter((c) => c.members.length > 1).length;
    const matched = recs.filter((r) => r.match).length;
    const scores = recs.map((r) => Number(r.total_score || 0));

    const html = [
        panel({
            key: 'monitoring', step: 1, name: 'Monitoring', role: 'Collect',
            purpose: 'Watches primary sources — GitHub releases (pre-releases filtered out) and official engineering blogs — and pulls in everything published in the window. It judges nothing; it only makes sure nothing is missed.',
            headline: `<strong>${f.signals ?? sig.length}</strong> signals from <strong>${new Set(sig.map((x) => x.source)).size || '—'}</strong> sources`,
            body: monitoringChart(),
            foot: `Source file: <code>${escapeHtml(state.signals?.source || s.source_signals || '')}</code>. Hover a column for the titles.`
        }),
        panel({
            key: 'clustering', step: 2, name: 'Clustering', role: 'Group',
            purpose: 'Folds signals about the same event into one trend, so a release announced on GitHub and on a blog is not counted twice. Rare identifiers are matched first, then titles at ≥ 0.75 similarity.',
            headline: `<strong>${f.signals ?? '—'}</strong> → <strong>${f.clusters ?? '—'}</strong> · ${merges} merge${merges === 1 ? '' : 's'}`,
            body: clusteringChart(),
            foot: `Only the first <strong>${f.evaluated ?? '—'}</strong> of ${f.clusters ?? '—'} clusters went on to verification in this capture (run with a limit to control API spend).`
        }),
        panel({
            key: 'verification', step: 3, name: 'Verification', role: 'Prove it is real',
            purpose: 'Checks each trend against the source itself — does the repo exist, is the release tag really there — so fabricated or hallucinated trends are stopped. Confidence is computed in Python from those facts, not reported by the model.',
            headline: `<strong>${f.evaluated ?? '—'}</strong> verified · <strong>${f.duplicates_collapsed ?? 0}</strong> duplicates collapsed`,
            body: verificationChart(),
            foot: 'Each dot is one trend. Stacked dots share the same confidence. Hover for the evidence note.'
        }),
        panel({
            key: 'curriculum', step: 4, name: 'Curriculum', role: 'Find what we teach',
            purpose: 'Searches the course slides and lab notebooks (RAG over the vector store) for material the trend touches, and cites the exact slide or notebook cell. An exact identifier hit beats a similarity score.',
            headline: `<strong>${matched}</strong> of ${recs.length} trends touch existing material`,
            body: curriculumChart()
        }),
        panel({
            key: 'evaluation', step: 5, name: 'Evaluation', role: 'Score',
            purpose: 'Turns the evidence into two 1–5 scores: maturity (how established the trend is) and relevance (how directly it hits what we teach). Their average is the total score that drives the tier.',
            headline: `scores <strong>${Math.min(...scores).toFixed(1)}</strong>–<strong>${Math.max(...scores).toFixed(1)}</strong> out of 5`,
            body: evaluationChart()
        }),
        panel({
            key: 'recommendation', step: 6, name: 'Recommendation', role: 'Decide & explain',
            purpose: 'Routes each scored trend through fixed gates to one of five action tiers, then writes a concrete plan that cites the slide or cell. It recommends; a human approves.',
            headline: `<strong>${s.actionable ?? '—'}</strong> actionable · <strong>${recs.length - (s.actionable || 0)}</strong> watch`,
            body: recommendationChart(),
            foot: 'Band width = number of trends. Hover a band to see which trends took that path.'
        })
    ].join('');

    $('agentSections').innerHTML = html;
    $('clusterReplay')?.addEventListener('click', playClustering);
    observePanels();
}

// ---------------------------------------------------------------------------
// reveal-on-scroll
// ---------------------------------------------------------------------------

let observer = null;
function observePanels() {
    observer?.disconnect();
    const panels = document.querySelectorAll('.agent-panel');
    if (reduceMotion || !('IntersectionObserver' in window)) {
        panels.forEach((p) => p.classList.add('in-view'));
        playClustering();
        return;
    }
    observer = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
            if (!e.isIntersecting) return;
            e.target.classList.add('in-view');
            if (e.target.id === 'agent-clustering') playClustering();
            observer.unobserve(e.target);
        });
    }, { threshold: 0.25 });
    panels.forEach((p) => observer.observe(p));
}

function replayAll() {
    document.querySelectorAll('.agent-panel').forEach((p) => p.classList.remove('in-view'));
    const flow = $('pipelineFlow');
    flow.classList.remove('run');
    void flow.offsetWidth;   // restart CSS animations
    flow.classList.add('run');
    renderSummaryCards(state.summary);
    observePanels();
}

// ---------------------------------------------------------------------------
// tooltip (pointer + keyboard)
// ---------------------------------------------------------------------------

const tooltip = $('tooltip');
function showTip(el, x, y) {
    const html = tips[Number(el.dataset.tip)];
    if (html === undefined) return;
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    const r = tooltip.getBoundingClientRect();
    const left = Math.min(Math.max(8, x + 14), window.innerWidth - r.width - 8);
    const top = y + 16 + r.height > window.innerHeight ? y - r.height - 12 : y + 16;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
}
document.addEventListener('pointermove', (e) => {
    const el = e.target.closest?.('[data-tip]');
    if (el) showTip(el, e.clientX, e.clientY); else tooltip.hidden = true;
});
document.addEventListener('focusin', (e) => {
    const el = e.target.closest?.('[data-tip]');
    if (!el) { tooltip.hidden = true; return; }
    const r = el.getBoundingClientRect();
    showTip(el, r.left + r.width / 2, r.bottom);
});
document.addEventListener('focusout', () => { tooltip.hidden = true; });
window.addEventListener('scroll', () => { tooltip.hidden = true; }, { passive: true });

// ---------------------------------------------------------------------------
// tiers + recommendation cards
// ---------------------------------------------------------------------------

function renderTierBar(summary) {
    // /summary returns tier_counts as a LIST of {tier,label,count} in TIER_ORDER.
    const list = Array.isArray(summary.tier_counts)
        ? summary.tier_counts
        : Object.entries(summary.tier_counts || {}).map(([tier, count]) => ({ tier, count }));
    const counts = Object.fromEntries(list.map((t) => [t.tier, Number(t.count) || 0]));
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;

    $('tierBar').innerHTML = TIER_ORDER.filter((t) => counts[t]).map((t, i) => `
        <div class="tier-segment grow-x" style="background:${tierFill(t)};color:${tierInk(t)};flex:${counts[t]} 1 0;--d:${i * 90}ms"
          ${tip(`<strong>${tierLabel(t)}</strong><br>${counts[t]} of ${total} recommendations`)}>${counts[t]}</div>`).join('');

    $('tierLegend').innerHTML = TIER_ORDER.map((t) => `
        <span class="legend-item ${counts[t] ? '' : 'dimmed'}">
          <span class="legend-swatch" style="background:${tierFill(t)}"></span>${tierLabel(t)} <strong>${counts[t] || 0}</strong>
        </span>`).join('');
}

function getVisibleRecommendations() {
    let items = [...state.recommendations];
    if (state.filter === 'actionable') items = items.filter((i) => i.recommended_action !== 'watch');
    if (state.filter === 'lab') items = items.filter((i) => i.match?.content_type === 'lab');
    if (state.filter === 'slides') items = items.filter((i) => i.match?.content_type === 'slides');
    return items;
}

function renderRecommendations() {
    const recList = $('recommendationList');
    const visible = getVisibleRecommendations();
    if (!visible.length) {
        recList.innerHTML = '<div class="empty-state">No recommendations match the current filters.</div>';
        return;
    }
    recList.innerHTML = visible.map((rec) => {
        const match = rec.match || {};
        const evidence = Array.isArray(rec.evidence) ? rec.evidence : [];
        const actionPlan = Array.isArray(rec.action_plan) ? rec.action_plan : [];
        const evidenceHtml = evidence.length
            ? evidence.map((item) => `
                <li class="evidence-item">
                  <strong>${escapeHtml(item.tier || 'Source')}</strong>
                  ${(item.url || item.source || '').startsWith('http')
                      ? `<a href="${escapeHtml(item.url || item.source)}" class="source-link" target="_blank" rel="noreferrer">${escapeHtml(item.source || item.url)}</a>`
                      : `<div class="source-link">${escapeHtml(item.source || 'Source')}</div>`}
                  <p>${escapeHtml(item.note || 'No note available.')}</p>
                </li>`).join('')
            : '<li class="evidence-item"><p>No evidence was attached to this recommendation.</p></li>';

        return `
        <article class="rec-card">
          <div class="rec-header">
            <div>
              <span class="tier-badge" style="background:${tierFill(rec.recommended_action)};color:${tierInk(rec.recommended_action)}">${escapeHtml(tierLabel(rec.recommended_action))}</span>
              <h4 class="rec-title">${escapeHtml(rec.trend || 'Untitled recommendation')}</h4>
            </div>
            <div class="rec-score"><strong>${Number(rec.total_score ?? 0).toFixed(1)}</strong> / 5</div>
          </div>
          <div class="rec-meta">
            <span>Confidence: ${(Number(rec.confidence ?? 0) * 100).toFixed(0)}%</span>
            ${match.week != null ? `<span>Week ${match.week}</span><span>${escapeHtml((match.content_type || '').toUpperCase())}</span><span>${escapeHtml(match.source_file || '')}</span>` : '<span>No curriculum match</span>'}
          </div>
          <p class="rec-note">${escapeHtml(rec.verification_note || 'No verification note supplied.')}</p>
          ${match.citation ? `<div class="citation-box"><strong>Citation</strong><div class="citation-value">${escapeHtml(match.citation)}</div></div>` : ''}
          <ul class="plan-list">
            ${actionPlan.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No recommended action steps available.</li>'}
          </ul>
          <details class="rec-details">
            <summary>Evidence and matched excerpt</summary>
            <div class="detail-body">
              <div class="detail-section"><h5>Evidence</h5><ul class="evidence-list">${evidenceHtml}</ul></div>
              ${match.matched_text ? `<div class="detail-section"><h5>Curriculum match</h5><pre class="match-preview">${escapeHtml(match.matched_text)}</pre></div>` : ''}
            </div>
          </details>
        </article>`;
    }).join('');
}

// ---------------------------------------------------------------------------
// load
// ---------------------------------------------------------------------------

async function loadDashboard() {
    try {
        const [summary, recResponse, tiers] = await Promise.all([
            fetchJson('/summary'),
            fetchJson('/recommendations'),
            fetchJson('/tiers').catch(() => null)
        ]);
        // /signals feeds two panels only; the rest of the page must not die with it.
        state.signals = await fetchJson('/signals').catch(() => null);

        if (Array.isArray(tiers) && tiers.length) {
            TIER_ORDER = tiers.map((t) => t.tier);
            TIER_LABEL = Object.fromEntries(tiers.map((t) => [t.tier, t.label]));
        }
        state.summary = summary;
        state.recommendations = Array.isArray(recResponse.recommendations) ? recResponse.recommendations : [];

        $('runTitle').textContent = `Run captured ${formatDate(summary.captured_at)}`;
        $('runMeta').textContent = `Source: ${summary.source_signals || 'Unknown'} • ${state.recommendations.length} recommendations in this snapshot`;

        pickRamp();
        renderSummaryCards(summary);
        renderFlow();
        renderAgents();
        renderTierBar(summary);
        renderRecommendations();
        $('pipelineFlow').classList.add('run');
    } catch (error) {
        $('runTitle').textContent = 'Snapshot unavailable';
        $('runMeta').textContent = 'The UI3 dashboard could not load the recorded data.';
        $('recommendationList').innerHTML = `
          <div class="error-state"><h4>Unable to load the recommendation snapshot.</h4><div>${escapeHtml(error.message)}</div></div>`;
    }
}

loadDashboard();
