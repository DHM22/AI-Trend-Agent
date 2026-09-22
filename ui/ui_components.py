"""Reusable presentation components. All backend strings are HTML escaped."""

from __future__ import annotations

from html import escape

import streamlit as st


CSS = """
<style>
:root{--bg:#080c17;--panel:#111827;--line:#26344a;--text:#f0f4ff;--muted:#a7b5cc;--violet:#a78bfa;--cyan:#67e8f9;--green:#34d399;--amber:#fbbf24;--rose:#f0abfc}
html,body,[data-testid="stApp"],[data-testid="stAppViewContainer"]{background:#080c17;color:var(--text)}
[data-testid="stAppViewContainer"]{background:radial-gradient(circle at 8% 4%,#282047 0,transparent 31%),radial-gradient(circle at 92% 8%,#103047 0,transparent 27%),#080c17}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1480px;padding-top:1.5rem;padding-bottom:5rem}
h1,h2,h3{letter-spacing:-.04em} p{line-height:1.6}
[data-testid="stButton"] button{border-radius:12px;min-height:42px;font-weight:650;transition:transform .2s,box-shadow .2s,border-color .2s}
[data-testid="stButton"] button:hover{transform:translateY(-2px);box-shadow:0 10px 25px #0005;border-color:#7c8fab}
[data-testid="stButton"] button[kind="primary"]{background:linear-gradient(105deg,#7c3aed,#315bdc);border:1px solid #a78bfa;color:white}
[data-testid="stFileUploader"]{border:1px dashed #617497;border-radius:20px;background:#111827a8;padding:12px}
[data-testid="stExpander"]{border:1px solid #2a3950;border-radius:14px;background:#111827aa}
[data-testid="stSelectbox"]>div>div,[data-testid="stTextInput"]>div>div{border-radius:12px}
.sr-brand{font-weight:800;letter-spacing:-.06em;font-size:1.35rem;color:#f6f4ff}
.sr-brand-mark{display:inline-grid;place-items:center;width:34px;height:34px;margin-right:9px;border-radius:10px;background:linear-gradient(145deg,#974cf4,#36b4e8);color:white;box-shadow:0 0 22px #8b5cf64c}
.sr-topline{display:flex;justify-content:space-between;align-items:center;padding:5px 0 13px;border-bottom:1px solid #ffffff18;margin-bottom:12px}
.sr-data-tag{border:1px solid #67e8f955;border-radius:100px;color:#a9eaf4;padding:6px 12px;font-size:.74rem;letter-spacing:.08em;font-weight:750}
.sr-eyebrow{font-size:.78rem;letter-spacing:.16em;text-transform:uppercase;font-weight:800;color:#92a6c6;margin-bottom:12px}
.sr-hero-title{font-size:clamp(3.9rem,7vw,7.2rem);line-height:.98;letter-spacing:-.075em;margin:20px 0;color:#fff;font-weight:800}
.sr-gradient{background:linear-gradient(110deg,#fff 5%,#bea7ff 51%,#6de4fb 100%);background-clip:text;-webkit-background-clip:text;color:transparent}
.sr-hero-copy{font-size:1.18rem;color:#bfcbdd;max-width:620px;line-height:1.75}
.sr-page-title{font-size:clamp(2.5rem,4vw,4.7rem);line-height:1.04;letter-spacing:-.065em;font-weight:800;color:#fff;margin:8px 0 14px}
.sr-lead{font-size:1.08rem;color:#b8c5d9;max-width:780px;margin-bottom:25px}
.sr-section{margin-top:46px;margin-bottom:20px}
.sr-section h2{font-size:clamp(1.55rem,2.4vw,2.35rem);margin:2px 0 8px;color:#fff}
.sr-section p{color:#aab9ce;margin:0}
.sr-glass{background:linear-gradient(150deg,#1d2739e8,#101827dd);border:1px solid #ffffff20;border-radius:22px;padding:26px;box-shadow:0 20px 60px #0003;transition:transform .25s,border-color .25s,box-shadow .25s;backdrop-filter:blur(16px)}
.sr-glass:hover{transform:translateY(-3px);border-color:#9483c777;box-shadow:0 22px 55px #0007}
.sr-glass.selected{border-color:#9e80ee;box-shadow:0 0 0 1px #8767e188,0 15px 45px #7c3aed2b}
.sr-kicker{font-size:.75rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#90a3bf}
.sr-card-title{font-size:1.23rem;font-weight:750;color:#fff;line-height:1.35;margin:11px 0 8px;overflow-wrap:anywhere}
.sr-card-copy{font-size:.9rem;color:#aebed2;line-height:1.55;min-height:56px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.sr-pill{display:inline-flex;align-items:center;gap:6px;border-radius:100px;padding:6px 10px;font-size:.72rem;letter-spacing:.05em;font-weight:780;text-transform:uppercase;border:1px solid #ffffff29;background:#ffffff0b;color:#d8e3f4}
.sr-pill.violet{color:#d3c0ff;border-color:#a78bfa66;background:#a78bfa1c}.sr-pill.cyan{color:#a0edfa;border-color:#67e8f966;background:#67e8f91c}.sr-pill.green{color:#83e9bc;border-color:#34d39966;background:#34d3991c}.sr-pill.amber{color:#ffd988;border-color:#fbbf2466;background:#fbbf241c}.sr-pill.rose{color:#fac8f9;border-color:#f0abfc66;background:#f0abfc1c}
.sr-metric-number{font-size:clamp(2.1rem,3.5vw,3.65rem);font-weight:800;letter-spacing:-.07em;color:#fff;line-height:1;margin:12px 0}
.sr-metric-label{font-size:.88rem;color:#a9bad0}
.sr-pipeline{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin:27px 0 35px}
.sr-step{position:relative;background:#111b2bdc;border:1px solid #ffffff18;border-radius:14px;padding:14px 13px;min-height:90px}
.sr-step.active{background:linear-gradient(135deg,#392568,#153a64);border-color:#a78bfa99;box-shadow:0 0 28px #8b5cf638}
.sr-step-num{font-size:.69rem;letter-spacing:.14em;color:#87a4ca;font-weight:800}.sr-step-name{font-size:.92rem;font-weight:800;color:white;margin-top:5px}.sr-step-desc{font-size:.73rem;color:#aebed2;margin-top:3px}
.sr-radar{height:410px;position:relative;display:grid;place-items:center;overflow:hidden;border-radius:28px;background:radial-gradient(circle,#271c55 0,#121b37 36%,#0c1325 75%);border:1px solid #9481d34d;box-shadow:inset 0 0 60px #6a4cc62b,0 25px 70px #0008}
.sr-radar::before{content:"";position:absolute;width:350px;height:350px;border:1px solid #8c84d158;border-radius:50%;box-shadow:0 0 0 55px #815dcb0b,0 0 0 110px #815dcb08}
.sr-radar::after{content:"";position:absolute;width:1px;height:380px;background:linear-gradient(transparent,#a78bfa44,transparent);transform:rotate(46deg)}
.sr-radar-sweep{position:absolute;width:360px;height:360px;border-radius:50%;background:conic-gradient(from 80deg,transparent 0deg,transparent 285deg,#7c3aed25 340deg,#67e8f955 359deg);animation:sr-sweep 12s linear infinite}
.sr-radar-core{z-index:2;width:132px;height:132px;border-radius:50%;display:grid;place-items:center;text-align:center;background:radial-gradient(circle at 40% 30%,#9c74ff,#4c2b92 68%,#271a57);border:2px solid #c4b5fd88;box-shadow:0 0 45px #855cf470;color:white;font-size:1.05rem;font-weight:800;line-height:1.2}
.sr-dot{position:absolute;width:10px;height:10px;border-radius:50%;background:#71e8fa;box-shadow:0 0 13px #71e8fa,0 0 27px #71e8fa;z-index:2}.sr-dot.d2{background:#c39aff;box-shadow:0 0 15px #b58aff,0 0 25px #b58aff}.sr-dot.d3{background:#66e0af;box-shadow:0 0 15px #66e0af}
.sr-radar-caption{position:absolute;left:20px;bottom:16px;z-index:3;color:#aebed2;font-size:.75rem;letter-spacing:.11em;text-transform:uppercase}
.sr-data-radar{height:520px;position:relative;overflow:hidden;border-radius:26px;border:1px solid #8f7bcc55;background:radial-gradient(circle at center,#2b2055 0,#15243b 25%,#0d1526 66%);box-shadow:inset 0 0 80px #7254a420,0 22px 60px #0006}
.sr-data-grid{position:absolute;inset:8%;border-radius:50%;border:1px solid #a3a5da48;box-shadow:0 0 0 75px #8c84d10a,0 0 0 150px #8c84d108;pointer-events:none}
.sr-data-grid::before,.sr-data-grid::after{content:"";position:absolute;left:50%;top:0;bottom:0;border-left:1px solid #7f96b126}.sr-data-grid::after{transform:rotate(90deg)}
.sr-data-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:110px;height:110px;border-radius:50%;display:grid;place-items:center;text-align:center;font-size:.9rem;line-height:1.25;font-weight:800;letter-spacing:.06em;color:white;background:radial-gradient(circle at 35% 20%,#9d75f5,#49317c);border:2px solid #d4bfff9c;box-shadow:0 0 45px #9061ed6e;z-index:3}
.sr-data-node{position:absolute;display:block;transform:translate(-50%,-50%);border-radius:50%;border:2px solid #f6f8ff;z-index:4;background:var(--node-color);box-shadow:0 0 0 8px color-mix(in srgb,var(--node-color) 16%,transparent),0 0 var(--node-glow) var(--node-color);transition:transform .2s,box-shadow .2s}
.sr-data-node:hover,.sr-data-node:focus{transform:translate(-50%,-50%) scale(1.45);box-shadow:0 0 0 13px color-mix(in srgb,var(--node-color) 23%,transparent),0 0 35px var(--node-color);outline:none}
.sr-data-node span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
.sr-data-caption{position:absolute;left:23px;bottom:17px;color:#b6c8df;font-size:.72rem;font-weight:800;letter-spacing:.14em;z-index:4}
.sr-radar-legend{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0;color:#adbed3;font-size:.78rem}.sr-radar-legend div{display:flex;align-items:center;gap:7px}.sr-radar-legend i{display:inline-block;width:9px;height:9px;border-radius:50%;box-shadow:0 0 10px currentColor}
.sr-flow{display:flex;align-items:stretch;gap:12px;flex-wrap:wrap}.sr-flow-item{flex:1;min-width:170px}.sr-flow-arrow{display:flex;align-items:center;color:#8b78c3;font-size:1.65rem}
.sr-timeline{border-left:2px solid #7564af;margin:12px 0 12px 15px;padding-left:24px}.sr-timeline-item{position:relative;margin:0 0 20px;padding:13px 18px;background:#151e30;border:1px solid #ffffff17;border-radius:14px}.sr-timeline-item::before{content:"";position:absolute;left:-32px;top:22px;width:12px;height:12px;border-radius:50%;background:#67e8f9;box-shadow:0 0 13px #67e8f9}
.sr-ring-wrap{display:flex;justify-content:center;padding:18px 0}.sr-ring{--pct:0%;--ring-color:#a78bfa;width:190px;height:190px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--ring-color) var(--pct),#29354d 0);box-shadow:0 0 40px color-mix(in srgb,var(--ring-color) 20%,transparent)}.sr-ring-inner{width:158px;height:158px;border-radius:50%;background:#101827;display:flex;flex-direction:column;justify-content:center;align-items:center}.sr-ring-value{font-size:2.7rem;font-weight:800;letter-spacing:-.07em;color:white}.sr-ring-denom{font-size:.9rem;color:#b5c4d8}.sr-ring-label{margin-top:7px;font-size:.75rem;font-weight:800;letter-spacing:.16em;color:#c5d2e5}
.sr-decision{padding:42px;border-radius:28px;background:linear-gradient(135deg,#2b1e52,#172648 52%,#101f36);border:1px solid #a78bfa88;box-shadow:0 25px 70px #0008,0 0 60px #7c3aed20}.sr-decision.green{border-color:#34d3998a;background:linear-gradient(135deg,#173e3b,#172648 60%,#0f202b)}.sr-decision.amber{border-color:#fbbf248a;background:linear-gradient(135deg,#4a351d,#252945 60%,#111a2b)}.sr-decision-title{font-size:clamp(2.2rem,4vw,4.1rem);font-weight:800;line-height:1.08;letter-spacing:-.06em;color:white;margin:17px 0}.sr-decision-copy{color:#c9d7e9;font-size:1.08rem;max-width:800px}
.sr-compare{min-height:270px}.sr-compare-label{font-size:.73rem;letter-spacing:.15em;font-weight:800;color:#94a8c7}.sr-compare-title{font-size:clamp(1.3rem,2vw,2rem);font-weight:800;color:#fff;line-height:1.25;margin:20px 0}.sr-compare-text{font-size:.95rem;color:#bbcadb;line-height:1.55}
.sr-reveal{border:1px solid #ffffff28;border-radius:18px;padding:22px 25px;margin:20px 0;background:linear-gradient(110deg,#30235f,#162746);font-size:1.55rem;font-weight:800;letter-spacing:-.03em;color:#fff}.sr-reveal.green{background:linear-gradient(110deg,#14433c,#173048);border-color:#34d39966}.sr-reveal.amber{background:linear-gradient(110deg,#4b351a,#242a47);border-color:#fbbf2466}
.sr-empty{padding:32px;border:1px dashed #60718e;border-radius:19px;color:#b7c5d9;background:#141d2bb8}
@keyframes sr-sweep{to{transform:rotate(360deg)}}
@media(max-width:850px){.sr-pipeline{display:flex;overflow-x:auto;padding-bottom:7px}.sr-step{min-width:140px;min-height:82px}.sr-radar{height:330px}.sr-data-radar{height:360px}.sr-flow-arrow{display:none}.sr-hero-title{font-size:3.7rem}.sr-decision{padding:26px}}
@media(prefers-reduced-motion:reduce){.sr-radar-sweep{animation:none}.sr-glass,[data-testid="stButton"] button{transition:none}}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def e(value: object) -> str:
    return escape(str(value) if value is not None else "", quote=True)


def brand() -> None:
    st.html('<div class="sr-topline"><div class="sr-brand"><span class="sr-brand-mark">✦</span>SkillRadar <span style="color:#a78bfa">AI</span></div><span class="sr-data-tag">RECORDED RUN · OFFLINE</span></div>')


STAGES = [
    ("Discover", "Signals appear"),
    ("Verify", "Is it real?"),
    ("Compare", "Is it taught?"),
    ("Evaluate", "How important?"),
    ("Decide", "What should change?"),
]


def pipeline(active: str | None) -> None:
    steps = "".join(
        f'<div class="sr-step {"active" if name == active else ""}"><div class="sr-step-num">0{i}</div><div class="sr-step-name">{name}</div><div class="sr-step-desc">{description}</div></div>'
        for i, (name, description) in enumerate(STAGES, 1)
    )
    st.html(f'<div class="sr-pipeline">{steps}</div>')


def page_intro(kicker: str, title: str, subtitle: str) -> None:
    st.html(f'<div class="sr-eyebrow">{e(kicker)}</div><div class="sr-page-title">{e(title)}</div><p class="sr-lead">{e(subtitle)}</p>')


def section(title: str, subtitle: str = "", kicker: str = "THE STORY") -> None:
    st.html(f'<div class="sr-section"><div class="sr-eyebrow">{e(kicker)}</div><h2>{e(title)}</h2><p>{e(subtitle)}</p></div>')


def pill(text: str, tone: str = "violet") -> str:
    return f'<span class="sr-pill {tone}">{e(text)}</span>'


def stat(value: object, label: str, note: str = "") -> None:
    st.html(f'<div class="sr-glass"><div class="sr-kicker">{e(note)}</div><div class="sr-metric-number">{e(value)}</div><div class="sr-metric-label">{e(label)}</div></div>')


def trend_card(record: dict, selected: bool = False, maturity: int | None = None) -> None:
    action = action_label(record.get("recommended_action", ""))
    confidence = record.get("confidence")
    pct = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—"
    evidence = len(record.get("evidence") or [])
    note = record.get("verification_note") or "Verification note unavailable."
    maturity_badge = pill(f"Current maturity {maturity}/5", "green") if maturity is not None else ""
    st.html(f'<div class="sr-glass {"selected" if selected else ""}"><div class="sr-kicker">RECORDED TREND · {e(pct)} CONFIDENCE</div><div class="sr-card-title">{e(record.get("trend", "Untitled"))}</div><div class="sr-card-copy">{e(note)}</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:18px">{pill(action,action_tone(record.get("recommended_action", "")))}{pill(f"{evidence} evidence item(s)","cyan")}{maturity_badge}</div></div>')


def action_label(action: str) -> str:
    return {"watch":"Keep watching", "update_existing_material":"Update existing material", "add_optional_content":"Add optional content", "add_new_lesson":"Create a new lesson", "investigate_larger_change":"Investigate larger change"}.get(action, action.replace("_", " ").title())


def action_tone(action: str) -> str:
    return {"watch":"amber", "update_existing_material":"violet", "add_optional_content":"cyan", "add_new_lesson":"green", "investigate_larger_change":"rose"}.get(action, "violet")


def score_ring(label: str, value: int | float, color: str) -> None:
    # The arc is a display-only fraction of the score returned by EvaluationAgent.
    percent = max(0.0, min(100.0, float(value) / 5 * 100))
    st.html(f'<div class="sr-ring-wrap"><div class="sr-ring" style="--pct:{percent:.1f}%;--ring-color:{color}"><div class="sr-ring-inner"><div class="sr-ring-value">{e(f"{value:g}")}</div><div class="sr-ring-denom">out of 5</div><div class="sr-ring-label">{e(label)}</div></div></div></div>')


def empty_state(title: str, detail: str) -> None:
    st.html(f'<div class="sr-empty"><div class="sr-card-title">{e(title)}</div><div class="sr-card-copy">{e(detail)}</div></div>')


def radar_art() -> None:
    dots = [("14%","26%",""),("74%","18%","d2"),("82%","66%","d3"),("22%","72%","d2"),("65%","80%",""),("39%","12%","d3")]
    points = "".join(f'<span class="sr-dot {tone}" style="left:{x};top:{y}"></span>' for x,y,tone in dots)
    st.html(f'<div class="sr-radar"><div class="sr-radar-sweep"></div>{points}<div class="sr-radar-core">SkillRadar<br>AI</div><div class="sr-radar-caption">Signal intelligence · recorded run</div></div>')
