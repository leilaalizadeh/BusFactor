"""BusFactor — Streamlit app (Teammate 4). Run: streamlit run app.py"""
from __future__ import annotations

import html
import json
import math
from functools import lru_cache
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402  (ships with streamlit)
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from busfactor import orchestrator as orc  # noqa: E402
from busfactor.llm_provider import LLMUnavailable, llm_available  # noqa: E402
from busfactor.missions import explain_mission  # noqa: E402
from busfactor.models import MissionStatus, ReviewStatus  # noqa: E402

PAGES = ["Overview", "1. Project Setup", "2. Private Check", "3. Team Coverage", "4. Teach Each Other",
         "5. Defense Retest", "6. Evidence & Limits"]
PAGE_HINTS = ["The demo at a glance", "Key decisions and sources", "Your own questions", "Who can explain what",
              "Peer-teaching missions", "New question, no hints", "Sources, log, limits"]

COVERAGE_PILL = {
    "covered": ("Covered", "green"),
    "single_point_of_failure": ("Single point of failure", "red"),
    "no_explainer": ("No explainer yet", "ink"),
    "not_assessed": ("Not assessed", "gray"),
}
CARD_PILL = {"verified": ("Verified", "green"), "proposed": ("Needs review", "amber"),
             "unsupported": ("No source", "red")}
MISSION_PILL = {"proposed": ("Waiting for consent", "amber"), "accepted": ("Accepted", "blue"),
                "completed": ("Retest not passed yet", "gray"), "verified": ("Transfer verified", "green"),
                "fallback": ("Ask the TA", "ink")}
EVIDENCE_PILL = {"demonstrated": ("Demonstrated", "green"), "needs_practice": ("Needs practice", "amber"),
                 "insufficient_evidence": ("Not assessed: no source", "gray")}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root {
  --bf-bg: #0A0F1F; --bf-surface: #121A33; --bf-fg: #E8EBF7; --bf-muted: #9AA4C7; --bf-line: #243058;
  --bf-accent: #6F88FF; --bf-accent-soft: rgba(111,136,255,.16); --bf-risk: #FF6B61; --bf-ok: #2BD99F; --bf-warn: #F5C46B;
  --bf-display: "Bricolage Grotesque", "IBM Plex Sans", system-ui, sans-serif;
  --bf-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --bf-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}

/* base */
.stApp { background: var(--bf-bg); }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp td, .stApp th {
  font-family: var(--bf-body);
}
.block-container { padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1080px; }
.stApp h1, .stApp h2, .stApp h3 { font-family: var(--bf-display); color: var(--bf-fg); letter-spacing: -0.02em; }
.stApp h1 { font-size: 2.35rem !important; font-weight: 700; line-height: 1.08; padding-bottom: 0.2rem; }
.stApp h2 { font-size: 1.35rem !important; font-weight: 700; }
.stApp h3 { font-size: 1.1rem !important; font-weight: 600; }

/* quiet Streamlit chrome for the demo */
header[data-testid="stHeader"] { background: transparent; }
.stAppDeployButton, [data-testid="stToolbarActions"], #MainMenu, footer { display: none !important; }

/* sidebar */
[data-testid="stSidebar"] { background: var(--bf-surface); border-right: 1px solid var(--bf-line); }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: var(--bf-muted); }
[data-testid="stSidebar"] .stRadio label p { font-weight: 500; }
.bf-brand { display: flex; align-items: center; gap: 10px; font: 700 1.25rem/1 var(--bf-display);
            letter-spacing: -0.01em; color: var(--bf-fg); margin: 0.2rem 0 0.4rem; }
.bf-brand svg { width: 22px; height: 22px; color: var(--bf-fg); }

/* cards = bordered containers */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][height] {
  background: var(--bf-surface); border-color: var(--bf-line) !important; border-radius: 12px !important;
}

/* metrics */
[data-testid="stMetricLabel"] p { font: 500 0.72rem/1.3 var(--bf-mono) !important; text-transform: uppercase;
                                  letter-spacing: 0.06em; color: var(--bf-muted); }
[data-testid="stMetricValue"] { font-family: var(--bf-display); font-weight: 700; letter-spacing: -0.02em;
                                font-variant-numeric: tabular-nums; }

/* controls */
.stButton button, .stFormSubmitButton button, .stDownloadButton button { border-radius: 8px; font-weight: 500; }
.stTextArea textarea, .stTextInput input { border-radius: 8px; }
[data-testid="stAlert"] { border-radius: 10px; }
[data-testid="stExpander"] details { border-radius: 10px; border-color: var(--bf-line); background: var(--bf-surface); }
[data-testid="stDataFrame"] { border: 1px solid var(--bf-line); border-radius: 10px; overflow: hidden; }
button[data-baseweb="tab"] p { font-weight: 500; }
hr { border-color: var(--bf-line) !important; }

/* BusFactor pieces */
div.bf-muted { padding-bottom: 0.35rem; }
.bf-pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font: 600 0.74rem/1.3 var(--bf-body);
           white-space: nowrap; }
.bf-green { background: #E5F5EC; color: #17784C; }
.bf-red   { background: #FCEBEA; color: #B3352C; }
.bf-amber { background: #FFF3DF; color: var(--bf-warn); }
.bf-blue  { background: var(--bf-accent-soft); color: var(--bf-accent); }
.bf-gray  { background: #EEF0F4; color: #4A5160; }
.bf-ink   { background: #23272F; color: #FFFFFF; }
.bf-step  { font: 500 0.72rem/1.3 var(--bf-mono); color: var(--bf-muted); text-transform: uppercase;
            letter-spacing: 0.08em; margin-bottom: -0.5rem; }
.bf-sub   { color: var(--bf-muted); font-size: 1.02rem; margin-top: -0.3rem; margin-bottom: 1.4rem; max-width: 46rem; }
.bf-quote { border-left: 2px solid var(--bf-accent); background: var(--bf-bg); padding: 0.65rem 0.95rem;
            border-radius: 0 8px 8px 0; font-size: 0.92rem; margin: 0.4rem 0; }
.bf-muted { color: var(--bf-muted); font-size: 0.86rem; }
.bf-badge { background: #FFF3DF; color: var(--bf-warn); border: 1px solid #F2D29B; border-radius: 10px;
            padding: 0.6rem 0.8rem; font: 600 0.78rem/1.45 var(--bf-body); margin: 0.6rem 0 1rem; }
.bf-badge b { font: 500 0.7rem/1.3 var(--bf-mono); letter-spacing: 0.06em; text-transform: uppercase; display: block; }
.bf-dots  { font-size: 1.1rem; letter-spacing: 0.2em; color: var(--bf-accent); }
.bf-question { background: var(--bf-bg); border: 1px solid var(--bf-line); border-radius: 10px; padding: 1rem 1.2rem;
               font: 500 1.04rem/1.5 var(--bf-body); margin: 0.5rem 0 0.9rem; }
.bf-title { font-weight: 600; font-size: 1.02rem; }

/* ---------- colour + motion ---------- */
@keyframes bf-rise  { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes bf-pulse { 0% { box-shadow: 0 0 0 0 rgba(214,69,59,.5); } 70% { box-shadow: 0 0 0 7px rgba(214,69,59,0); }
                      100% { box-shadow: 0 0 0 0 rgba(214,69,59,0); } }
@keyframes bf-march { to { background-position: 28px 0; } }
@keyframes bf-ring  { from { stroke-dashoffset: var(--from); } to { stroke-dashoffset: var(--to); } }
@keyframes bf-draw  { to { stroke-dashoffset: 0; } }
@keyframes bf-pop   { 0% { transform: scale(.7); opacity: 0; } 60% { transform: scale(1.06); opacity: 1; } 100% { transform: scale(1); } }

[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][height] { animation: bf-rise .45s ease both; }

.bf-hero { background: linear-gradient(120deg, #ECF0FF 0%, #F4F7FF 48%, #E8F6EF 100%); border: 1px solid #DCE3F5;
           border-radius: 16px; padding: 18px 24px 22px; margin: 0 0 1.4rem; animation: bf-rise .4s ease both; }
.bf-hero h1 { margin: 1rem 0 .3rem !important; padding: 0 !important; }
.bf-hero p { color: var(--bf-muted); margin: 0; max-width: 46rem; font-size: 1.02rem; }

.bf-stepper { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.bf-st { display: inline-flex; align-items: center; gap: 7px; font: 500 .78rem/1 var(--bf-body); color: var(--bf-muted); white-space: nowrap; }
.bf-st span { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; border: 1.5px solid #C9D0DC;
              background: #fff; font: 600 .68rem/1 var(--bf-mono); }
.bf-st.done span { background: var(--bf-accent-soft); border-color: var(--bf-accent); color: var(--bf-accent); }
.bf-st.now { color: var(--bf-fg); font-weight: 600; }
.bf-st.now span { background: var(--bf-accent); border-color: var(--bf-accent); color: #fff; box-shadow: 0 0 0 4px rgba(47,79,216,.16); }
.bf-stepper i { flex: 1 1 14px; max-width: 46px; height: 2px; border-radius: 2px; background: #D3D9E4; }
.bf-stepper i.done { background: var(--bf-accent); }

.bf-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: currentColor; margin-right: 6px;
          vertical-align: 1px; animation: bf-pulse 1.8s ease-out infinite; }

.bf-av { display: inline-grid; place-items: center; border-radius: 50%; background: var(--c); color: #fff !important; flex: none; line-height: 1;
         font-family: var(--bf-display); font-weight: 700; box-shadow: 0 0 0 3px #fff, 0 0 0 4px var(--c); }
.bf-me { display: flex; gap: 10px; align-items: center; background: var(--bf-bg); border: 1px solid var(--bf-line);
         border-radius: 10px; padding: 9px 11px; margin: -.2rem 0 .9rem; }
.bf-me b { display: block; font-size: .88rem; line-height: 1.3; } .bf-me div > span { display: block; font-size: .74rem; line-height: 1.35; color: var(--bf-muted); }

.bf-ring { position: relative; width: 176px; height: 176px; margin: 0 auto; }
.bf-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.bf-ring .trk { fill: none; stroke: #E5E9F0; stroke-width: 14; }
.bf-ring .val { fill: none; stroke: url(#bfg); stroke-width: 14; stroke-linecap: round;
                animation: bf-ring 1.4s cubic-bezier(.2,.7,.2,1) .25s both; }
.bf-ring .lbl { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.bf-ring .lbl b { font: 700 2.3rem/1 var(--bf-display); letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.bf-ring .lbl span { font: 500 .7rem/1.4 var(--bf-mono); color: var(--bf-muted); text-transform: uppercase; letter-spacing: .06em; margin-top: 4px; }

.bf-dots2 { display: flex; gap: 6px; margin-bottom: 4px; }
.bf-dots2 i { width: 11px; height: 11px; border-radius: 50%; border: 1.5px solid #C5CCD8; }
.bf-dots2.covered i.on { background: var(--bf-ok); border-color: var(--bf-ok); }
.bf-dots2.single_point_of_failure i.on { background: var(--bf-risk); border-color: var(--bf-risk); }

.bf-flow { display: flex; align-items: center; gap: 16px; margin: .5rem 0 .9rem; }
.bf-flow .who { display: flex; align-items: center; gap: 11px; position: relative; }
.bf-flow .who b { display: block; font-size: .95rem; }
.bf-flow .who span { font: 500 .68rem/1.3 var(--bf-mono); color: var(--bf-muted); text-transform: uppercase; letter-spacing: .07em; }
.bf-flow .ck { position: absolute; left: 27px; top: -5px; width: 18px; height: 18px; border-radius: 50%; background: var(--bf-ok);
               color: #fff; font: 700 .64rem/1 var(--bf-body); font-style: normal; display: grid; place-items: center;
               border: 2px solid #fff; animation: bf-pop .4s ease both; }
.bf-flow .arrow { flex: 1 1 60px; min-width: 50px; display: flex; align-items: center; }
.bf-flow .arrow i { flex: 1; height: 2px; background: repeating-linear-gradient(90deg, var(--bf-accent) 0 8px, transparent 8px 14px);
                    background-size: 28px 2px; animation: bf-march .9s linear infinite; }
.bf-flow .arrow::after { content: ""; border-left: 8px solid var(--bf-accent); border-top: 5px solid transparent; border-bottom: 5px solid transparent; }
.bf-flow .arrow.ok i { background: var(--bf-ok); animation: none; }
.bf-flow .arrow.ok::after { border-left-color: var(--bf-ok); }

.bf-win { display: flex; gap: 14px; align-items: center; background: linear-gradient(120deg, #E6F6EE, #EEF4FF);
          border: 1px solid #BFE3CF; border-radius: 12px; padding: 14px 16px; margin: .4rem 0 .6rem; animation: bf-pop .5s ease both; }
.bf-win svg { width: 44px; height: 44px; flex: none; }
.bf-win circle { fill: var(--bf-ok); }
.bf-win path { fill: none; stroke: #fff; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round;
               stroke-dasharray: 40; stroke-dashoffset: 40; animation: bf-draw .6s .35s ease forwards; }
.bf-win b { display: block; font-size: 1rem; } .bf-win span { color: var(--bf-muted); font-size: .9rem; }

/* ---------- dark sidebar ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0D1430 0%, #121B42 100%); border-right: none; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] .bf-brand,
[data-testid="stSidebar"] .bf-me b { color: #E8EBF7 !important; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p, [data-testid="stSidebar"] .bf-me div > span { color: #8D97BC !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div { background: rgba(255,255,255,.07); border-color: rgba(255,255,255,.14); }
[data-testid="stSidebar"] [data-baseweb="select"] * { color: #E8EBF7 !important; }
[data-testid="stSidebar"] .stButton button { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.16); color: #E8EBF7; }
[data-testid="stSidebar"] .stButton button:hover { border-color: #8FA5FF; color: #fff; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.1) !important; }
[data-testid="stSidebar"] .bf-me { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.1); }
[data-testid="stSidebar"] .bf-av { box-shadow: 0 0 0 3px #121B42, 0 0 0 4px var(--c); }
[data-testid="stSidebar"] .bf-brand svg { color: #fff; }
[data-testid="stSidebar"] [role="radiogroup"] label, [data-testid="stSidebar"] [role="radiogroup"] label * { color: #C9D0EA !important; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { background: transparent !important; border: 1.5px solid #56628F !important; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) > div:first-child { background: #2F4FD8 !important; border-color: #9DB0FF !important; }
[data-testid="stSidebar"] [role="radiogroup"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [role="radiogroup"] [data-testid="stCaptionContainer"] * { color: #7E89B1 !important; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) [data-testid="stMarkdownContainer"]:not([data-testid="stCaptionContainer"] *) p { color: #FFFFFF !important; font-weight: 600; }

/* ---------- overview ---------- */
.bf-dark { position: relative; overflow: hidden; border-radius: 18px; padding: 30px 32px 26px; margin-bottom: 1rem; color: #fff;
  background:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 32px 32px,
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 32px 32px,
    radial-gradient(900px 380px at 12% -20%, #2B44B0 0%, rgba(43,68,176,0) 62%),
    radial-gradient(700px 320px at 105% 120%, rgba(30,154,98,.5) 0%, rgba(30,154,98,0) 60%),
    #0A0F1F;
  animation: bf-rise .5s ease both; }
.bf-dark .kicker { font: 500 .74rem/1.4 var(--bf-mono); letter-spacing: .1em; text-transform: uppercase; color: #9FAAD6; }
.bf-dark h1 { color: #FFFFFF !important; font-size: clamp(2rem, 4vw, 3rem) !important; line-height: 1.05 !important;
              margin: .7rem 0 .8rem !important; padding: 0 !important; max-width: 46rem; }
.bf-dark h1 em { font-style: normal; background: linear-gradient(90deg, #93A8FF 0%, #46E0A8 100%);
                 -webkit-background-clip: text; background-clip: text; color: transparent; }
.bf-dark p { color: #B9C1E0; max-width: 40rem; margin: 0 0 1.4rem; font-size: 1.04rem; }
.bf-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.bf-kpi { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: 12px; padding: 14px 16px;
          backdrop-filter: blur(4px); animation: bf-rise .5s ease both; }
.bf-kpi:nth-child(2) { animation-delay: .08s; } .bf-kpi:nth-child(3) { animation-delay: .16s; } .bf-kpi:nth-child(4) { animation-delay: .24s; }
.bf-kpi .k { font: 500 .68rem/1.3 var(--bf-mono); letter-spacing: .08em; text-transform: uppercase; color: #9FAAD6; }
.bf-kpi .v { font: 700 2rem/1.1 var(--bf-display); letter-spacing: -.02em; color: #fff; margin-top: 6px; font-variant-numeric: tabular-nums; }
.bf-kpi .s { font-size: .8rem; color: #8D97BC; margin-top: 2px; }
.bf-kpi .s b { color: #46E0A8; font-weight: 600; }
.bf-kpi .s b.bad { color: #FF8A80; }

.bf-story { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: .4rem 0 1rem; }
.bf-sc { background: var(--bf-surface); border: 1px solid var(--bf-line); border-radius: 12px; padding: 14px 14px 16px;
         animation: bf-rise .45s ease both; min-width: 0; }
.bf-sc:nth-child(2) { animation-delay: .06s; } .bf-sc:nth-child(3) { animation-delay: .12s; }
.bf-sc:nth-child(4) { animation-delay: .18s; } .bf-sc:nth-child(5) { animation-delay: .24s; }
.bf-sc .n { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font: 600 .72rem/1 var(--bf-mono);
            border: 1.5px solid #C9D0DC; color: var(--bf-muted); background: #fff; }
.bf-sc.done .n { background: var(--bf-ok); border-color: var(--bf-ok); color: #fff; }
.bf-sc.next { border-color: var(--bf-accent); animation: bf-rise .45s ease both, bf-glow 2.2s ease-in-out .6s infinite; }
.bf-sc.next .n { background: var(--bf-accent); border-color: var(--bf-accent); color: #fff; }
.bf-sc h4 { font: 600 .95rem/1.3 var(--bf-body) !important; margin: .7rem 0 .25rem !important; padding: 0 !important; color: var(--bf-fg); }
.bf-sc p { font-size: .82rem; color: var(--bf-muted); margin: 0 0 .6rem; }
.bf-sc .st { font: 600 .68rem/1 var(--bf-mono); letter-spacing: .06em; text-transform: uppercase; }
.bf-sc.done .st { color: var(--bf-ok); } .bf-sc.next .st { color: var(--bf-accent); } .bf-sc .st { color: #9AA1AE; }
@keyframes bf-glow { 0%, 100% { box-shadow: 0 0 0 0 rgba(47,79,216,.0); } 50% { box-shadow: 0 0 0 5px rgba(47,79,216,.14); } }
@media (max-width: 900px) { .bf-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } .bf-story { grid-template-columns: minmax(0, 1fr); } }

/* ---------- every page matches the overview ---------- */
.bf-hero, .bf-panel {
  position: relative; overflow: hidden; border: none; color: #fff;
  background:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 32px 32px,
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 32px 32px,
    radial-gradient(800px 340px at 10% -30%, #2B44B0 0%, rgba(43,68,176,0) 62%),
    radial-gradient(600px 300px at 105% 130%, rgba(30,154,98,.45) 0%, rgba(30,154,98,0) 60%),
    #0A0F1F;
}
.bf-hero { border-radius: 18px; padding: 20px 28px 24px; }
.bf-hero h1 { color: #FFFFFF !important; margin: 1.1rem 0 .35rem !important; }
.bf-hero h1 em, .bf-grad { font-style: normal; background: linear-gradient(90deg, #93A8FF 0%, #46E0A8 100%);
                           -webkit-background-clip: text; background-clip: text; color: transparent; }
.bf-hero p { color: #B9C1E0; }
.bf-hero .bf-st { color: #8F9AC4; }
.bf-hero .bf-st span { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.22); color: #C9D0EA; }
.bf-hero .bf-st.done { color: #B9C1E0; }
.bf-hero .bf-st.done span { background: rgba(70,224,168,.14); border-color: #46E0A8; color: #46E0A8; }
.bf-hero .bf-st.now { color: #FFFFFF; }
.bf-hero .bf-st.now span { background: #4F6BFF; border-color: #A9B9FF; color: #fff; box-shadow: 0 0 0 4px rgba(79,107,255,.3); }
.bf-hero .bf-stepper i { background: rgba(255,255,255,.14); }
.bf-hero .bf-stepper i.done { background: #46E0A8; }

.bf-panel { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 28px; align-items: center;
            border-radius: 18px; padding: 22px 28px; margin: 0 0 1.2rem; animation: bf-rise .5s ease both; }
.bf-panel .bf-ring .trk { stroke: rgba(255,255,255,.1); }
.bf-panel .bf-ring .lbl b { color: #fff; }
.bf-panel .bf-ring .lbl span { color: #9FAAD6; }
.bf-pstats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.bf-pstats > div { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: 12px; padding: 14px 16px; }
.bf-pstats .k { font: 500 .68rem/1.3 var(--bf-mono); letter-spacing: .08em; text-transform: uppercase; color: #9FAAD6; }
.bf-pstats .v { font: 700 1.9rem/1.1 var(--bf-display); letter-spacing: -.02em; color: #fff; margin-top: 6px; font-variant-numeric: tabular-nums; }
.bf-pstats .s { font-size: .8rem; color: #8D97BC; margin-top: 2px; }
.bf-pstats .s b { color: #46E0A8; font-weight: 600; }
.bf-panel .note { grid-column: 1 / -1; font-size: .82rem; color: #8D97BC; margin-top: -6px; }
@media (max-width: 900px) { .bf-panel { grid-template-columns: minmax(0, 1fr); } .bf-pstats { grid-template-columns: minmax(0, 1fr); } }

[data-testid="stMetric"] { background: var(--bf-surface); border: 1px solid var(--bf-line); border-radius: 12px; padding: 14px 16px; }
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][height] { transition: transform .18s ease, box-shadow .18s ease; }
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][height]:hover {
  transform: translateY(-2px); box-shadow: 0 14px 30px -18px rgba(16,24,64,.35); }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(135deg, #4A66FF 0%, #2F4FD8 100%); border: none; box-shadow: 0 8px 20px -10px rgba(47,79,216,.8); }
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover { filter: brightness(1.08); }
.bf-question { background: #F3F5FF; border-color: #DCE3FF; }

/* ---------- dark page: the whole app matches the overview ---------- */
.stApp {
  background:
    radial-gradient(1100px 560px at 85% -10%, rgba(43,68,176,.32) 0%, rgba(43,68,176,0) 60%),
    radial-gradient(900px 520px at -10% 110%, rgba(30,154,98,.16) 0%, rgba(30,154,98,0) 60%),
    #0A0F1F;
  background-attachment: fixed;
}
[data-testid="stSidebar"] { border-right: 1px solid rgba(255,255,255,.06); }
.bf-hero, .bf-panel, .bf-dark { border: 1px solid rgba(255,255,255,.08); box-shadow: 0 24px 60px -30px rgba(0,0,0,.8); }
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][height] {
  background: rgba(18,26,51,.78) !important; border-color: var(--bf-line) !important; backdrop-filter: blur(6px); }
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][height]:hover {
  border-color: #33427A !important; box-shadow: 0 16px 36px -20px rgba(0,0,0,.9), 0 0 0 1px rgba(111,136,255,.12); }
[data-testid="stMetric"], [data-testid="stExpander"] details { background: rgba(18,26,51,.78); border-color: var(--bf-line); }

.bf-green { background: rgba(43,217,159,.14); color: #4BE3AE; }
.bf-red   { background: rgba(255,107,97,.15); color: #FF8A80; }
.bf-amber { background: rgba(245,196,107,.14); color: #F5C46B; }
.bf-blue  { background: rgba(111,136,255,.16); color: #A9B9FF; }
.bf-gray  { background: rgba(255,255,255,.08); color: #B5BDDC; }
.bf-ink   { background: #E8EBF7; color: #0A0F1F; }
.bf-badge { background: rgba(245,196,107,.1); color: #F5C46B; border-color: rgba(245,196,107,.35); }
.bf-quote { background: rgba(255,255,255,.04); }
.bf-question { background: rgba(111,136,255,.08); border-color: rgba(111,136,255,.28); color: var(--bf-fg); }
.bf-av { box-shadow: 0 0 0 3px #121A33, 0 0 0 4px var(--c); }
.bf-flow .ck { border-color: #121A33; color: #0A0F1F; }
.bf-ring .trk { stroke: rgba(255,255,255,.1); }
.bf-dots2 i { border-color: #3A4670; }
.bf-sc .n { background: transparent; border-color: #3A4670; }
.bf-sc.done .n, .bf-sc.next .n { color: #0A0F1F; }
.bf-sc.next { box-shadow: 0 0 0 1px rgba(111,136,255,.3); }
.bf-win { background: linear-gradient(120deg, rgba(43,217,159,.16), rgba(111,136,255,.12)); border-color: rgba(43,217,159,.35); }
.bf-win path { stroke: #0A0F1F; }
.bf-kpi .s b, .bf-pstats .s b { color: #4BE3AE; }
.stApp [data-testid="stCaptionContainer"] p { color: var(--bf-muted); }
@keyframes bf-glow { 0%, 100% { box-shadow: 0 0 0 1px rgba(111,136,255,.3); } 50% { box-shadow: 0 0 0 5px rgba(111,136,255,.18); } }

@media (prefers-reduced-motion: reduce) {
  .stApp *, .stApp *::before, .stApp *::after { animation: none !important; transition: none !important; }
  .bf-win path { stroke-dashoffset: 0; }
}
</style>
"""

BRAND = """<div class="bf-brand"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
<circle cx="5" cy="6" r="2.4" fill="currentColor"/><circle cx="19" cy="6" r="2.4" fill="currentColor"/>
<circle cx="5" cy="18" r="2.4" fill="currentColor"/><circle cx="19" cy="18" r="2.4" fill="currentColor"/>
<path d="M12 8.5 15.5 12 12 15.5 8.5 12Z" fill="#2F4FD8"/>
<path d="M7 7.3 10 10.3M17 7.3 14 10.3M7 16.7l3-3M17 16.7l-3-3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
</svg>BusFactor</div>"""

st.set_page_config(page_title="BusFactor", page_icon=":material/hub:", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
orc.ensure_seeded()
members = orc.members()
names = {m.id: m.display_name for m in members.values()}
cards = {d.id: d for d in orc.decisions()}


# ------------------------------------------------------------------ small UI helpers
def esc(text: object) -> str:
    return html.escape(str(text))


def pill(label: str, kind: str) -> str:
    dot = '<i class="bf-dot"></i>' if kind == "red" else ""   # red = needs attention: pulsing dot
    return f'<span class="bf-pill bf-{kind}">{dot}{esc(label)}</span>'


MEMBER_COLORS = ["#4F6BFF", "#14B8A6", "#F59E0B", "#D946EF", "#38BDF8", "#F87171"]


def avatar(member_id: str, size: int = 34) -> str:
    """Coloured initial for a member (colour is fixed per member id)."""
    order = sorted(names)
    color = MEMBER_COLORS[(order.index(member_id) if member_id in order else 0) % len(MEMBER_COLORS)]
    initial = names.get(member_id, member_id).split()[-1][:1]
    return (f'<span class="bf-av" style="--c:{color};width:{size}px;height:{size}px;'
            f'font-size:{round(size * 0.42)}px">{esc(initial)}</span>')


STEP_SHORT = ["Setup", "Check", "Coverage", "Teach", "Retest", "Evidence"]


def stepper(index: int) -> str:
    parts = []
    for i, name in enumerate(STEP_SHORT, 1):
        if i > 1:
            parts.append(f'<i class="{"done" if i <= index else ""}"></i>')
        state = "done" if i < index else "now" if i == index else ""
        parts.append(f'<div class="bf-st {state}"><span>{"✓" if i < index else i}</span>{name}</div>')
    return f'<div class="bf-stepper">{"".join(parts)}</div>'


def ring(num: int, den: int, base_num: int) -> str:
    """Coverage donut that animates from the baseline to the current value."""
    circ = 2 * math.pi * 62
    frac = num / den if den else 0
    start = circ * (1 - (base_num / den if den else 0))
    end = circ * (1 - frac)
    label = f"<b>{num}/{den}</b><span>{frac:.0%} covered</span>" if den else "<b>–</b><span>not measurable</span>"
    return (f'<div class="bf-ring"><svg viewBox="0 0 160 160" aria-hidden="true"><defs>'
            f'<linearGradient id="bfg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7189FF"/>'
            f'<stop offset="1" stop-color="#2BD99F"/></linearGradient></defs>'
            f'<circle cx="80" cy="80" r="62" class="trk"/>'
            f'<circle cx="80" cy="80" r="62" class="val" style="stroke-dasharray:{circ:.1f};--from:{start:.1f};'
            f'--to:{end:.1f};stroke-dashoffset:{end:.1f}"/></svg><div class="lbl">{label}</div></div>')


def win(title: str, text: str) -> str:
    return (f'<div class="bf-win"><svg viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/>'
            f'<path d="M15 27l7 7 15-16"/></svg><div><b>{esc(title)}</b><span>{esc(text)}</span></div></div>')


def flow(m) -> str:
    """Mentor -> learner with a moving arrow; ticks show who has accepted."""
    tick = lambda ok: '<em class="ck">✓</em>' if ok else ""  # noqa: E731
    done = "ok" if m.status == MissionStatus.verified else ""
    return (f'<div class="bf-flow">'
            f'<div class="who">{avatar(m.mentor_id, 40)}{tick(m.mentor_consent)}'
            f'<div><b>{esc(names[m.mentor_id])}</b><span>Mentor</span></div></div>'
            f'<div class="arrow {done}"><i></i></div>'
            f'<div class="who">{avatar(m.learner_id, 40)}{tick(m.learner_consent)}'
            f'<div><b>{esc(names[m.learner_id])}</b><span>Learner</span></div></div></div>')


def show(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def page_header(index: int, title: str, subtitle: str) -> None:
    head, _, tail = title.partition(" · ")
    heading = esc(head) + (f" <em>· {esc(tail)}</em>" if tail else "")
    show(f'<div class="bf-hero">{stepper(index)}<h1>{heading}</h1><p>{esc(subtitle)}</p></div>')


def coverage_text(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "not measurable"
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})"


def quote_block(ref) -> str:
    where = f"{esc(ref.file)} · page {ref.page}" + (f" · {esc(ref.section)}" if ref.section else "")
    return f'<div class="bf-quote">“{esc(ref.quote)}”<br><span class="bf-muted">{where}</span></div>'


@lru_cache(maxsize=1)
def _three_tag() -> str:
    """three.js from the repo (works offline at the venue); falls back to the CDN."""
    local = ROOT / "web" / "vendor" / "three.min.js"
    if local.exists():
        return "<script>" + local.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"
    return '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'


def knowledge_map(report, improved: list[str], height: int = 470) -> None:
    """3D map: one node per decision, one orbiting light per person who can explain it. Counts only."""
    template = (ROOT / "web" / "knowledge_map.html").read_text(encoding="utf-8")
    nodes = [{"id": c.decision_id, "title": cards[c.decision_id].title, "n": len(c.demonstrated_by), "status": c.status}
             for c in report.per_decision]
    data = json.dumps({"nodes": nodes, "improved": improved}).replace("</", "<\\/")
    components.html(template.replace("__THREE__", _three_tag()).replace("__DATA__", data), height=height)


def overview() -> None:
    report = orc.team_coverage()
    snaps = orc.coverage_snapshots()
    base = snaps[0] if snaps else {"numerator": report.numerator, "denominator": report.denominator,
                                     "spof": report.spof_decision_ids}
    status_now = {c.decision_id: c.status for c in report.per_decision}
    improved = [d for d in base.get("spof", []) if status_now.get(d) == "covered"]
    ms = orc.missions()
    accepted = [m for m in ms if m.status in (MissionStatus.accepted, MissionStatus.completed, MissionStatus.verified)]
    verified_missions = [m for m in ms if m.status == MissionStatus.verified]
    verified_cards = sum(d.review_status == ReviewStatus.verified for d in cards.values())
    p = orc.project()

    gained = report.numerator - base["numerator"]
    spof_drop = len(base.get("spof", [])) - len(report.spof_decision_ids)
    kpis = [
        ("Decision coverage", f"{report.numerator}/{report.denominator}" if report.denominator else "–",
         f'<b>+{gained}</b> since start' if gained > 0 else f'started at {base["numerator"]}/{base["denominator"]}'),
        ("Single points of failure", str(len(report.spof_decision_ids)),
         f'<b>−{spof_drop}</b> since start' if spof_drop > 0 else '<b class="bad">need a second explainer</b>'),
        ("Teaching missions", str(len(accepted)), f"{len(ms)} proposed · {len(verified_missions)} verified"),
        ("Decisions verified", f"{verified_cards}/{len(cards)}", "quotes checked on their page"),
    ]
    tiles = "".join(f'<div class="bf-kpi"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
                    for k, v, s in kpis)
    show(f'<div class="bf-dark"><div class="kicker">Live demo · {esc(p.title if p else "BusFactor")}</div>'
         f'<h1>You split the work.<br><em>Don\'t split the understanding.</em></h1>'
         f'<p>BusFactor finds the project decisions only one teammate can explain, sets up peer teaching between '
         f'teammates, and checks with a new question that the knowledge really moved.</p>'
         f'<div class="bf-kpis">{tiles}</div></div>')

    knowledge_map(report, improved)

    steps = [
        ("Find the decisions", verified_cards > 0, f"{verified_cards} of {len(cards)} cards verified against the report"),
        ("Ask privately", report.denominator > 0, f"{report.denominator} decisions have private answers"),
        ("Spot the risk", bool(base.get("spof")), f"{len(base.get('spof', []))} decisions depended on one person"),
        ("Teach each other", bool(accepted), f"{len(accepted)} mission(s) accepted by both people"),
        ("Check again", bool(verified_missions),
         f"{len(verified_missions)} transfer(s) verified · coverage {base['numerator']}/{base['denominator']} → "
         f"{report.numerator}/{report.denominator}"),
    ]
    first_open = next((i for i, (_, done, _) in enumerate(steps) if not done), None)
    html_steps = []
    for i, (title, done, detail) in enumerate(steps):
        cls, state = ("done", "Done") if done else (("next", "Up next") if i == first_open else ("", "Waiting"))
        html_steps.append(f'<div class="bf-sc {cls}"><div class="n">{"✓" if done else i + 1}</div>'
                          f'<h4>{title}</h4><p>{esc(detail)}</p><div class="st">{state}</div></div>')
    st.subheader("Demo story")
    show(f'<div class="bf-story">{"".join(html_steps)}</div>')
    show('<div class="bf-muted">All numbers come from the synthetic demo data and update live as you use the app.</div>')


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    show(BRAND)
    st.caption("Your grade is shared. Your understanding shouldn't be isolated.")
    badge = orc.demo_banner()
    if badge:
        show(f'<div class="bf-badge"><b>{esc(badge)}</b>Fictional project, members and answers.</div>')
    # Optional deep links for demos and screenshots, e.g. ?page=3&as=M04
    qp_page, qp_as = st.query_params.get("page", ""), st.query_params.get("as", "")
    start_page = int(qp_page) if qp_page.isdigit() and 0 <= int(qp_page) < len(PAGES) else 0
    member_ids = list(members)
    viewer = st.selectbox("Who are you?", member_ids, format_func=lambda m: f"{names[m]} ({m})",
                          index=member_ids.index(qp_as) if qp_as in member_ids else 0)
    show(f'<div class="bf-me">{avatar(viewer, 30)}<div><b>{esc(names[viewer])}</b>'
         '<span>You see only your own answers</span></div></div>')
    page = st.radio("Go to", PAGES, captions=PAGE_HINTS, index=start_page)
    st.divider()
    st.caption("Grader: " + ("live model" if llm_available() else "demo keyword rubric (offline)"))
    if st.button("Reset demo data", width="stretch"):
        orc.seed_demo_data()
        st.rerun()


# ------------------------------------------------------------------ 0. overview
if page == PAGES[0]:
    overview()

# ------------------------------------------------------------------ 1. setup
elif page == PAGES[1]:
    p = orc.project()
    page_header(1, p.title if p else "Project Setup",
                "The key decisions of the project. Each one is linked to the exact page it comes from.")
    if p:
        show(f'<div class="bf-muted">{esc(p.course)} · source: {esc(", ".join(p.source_files))}</div>')

    with st.expander("Upload a different project file"):
        upload = st.file_uploader("PDF, Markdown or text. Only upload files you are allowed to share.",
                                  type=["pdf", "md", "txt"])
        if upload and st.button("Extract decision cards", type="primary"):
            dest = ROOT / "uploads" / Path(upload.name).name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(upload.getvalue())
            try:
                orc.setup_project([str(dest)], actor=viewer)
                st.success("Cards extracted. Cards without a verified quote can't be confirmed.")
                st.rerun()
            except (LLMUnavailable, RuntimeError, ValueError) as err:
                st.error(f"Extraction failed: {err}")

    verified = sum(d.review_status == ReviewStatus.verified for d in cards.values())
    c1, c2, c3 = st.columns(3)
    c1.metric("Decisions", len(cards))
    c2.metric("Verified", verified)
    c3.metric("Without a source", sum(not d.source_refs for d in cards.values()))

    for d in cards.values():
        with st.container(border=True):
            label, kind = CARD_PILL[d.review_status.value]
            left, right = st.columns([5, 1.4])
            left.markdown(f"**{d.id} · {d.title}**")
            with right:
                show(pill(label, kind))
            st.write(d.rationale)
            info = []
            if d.alternatives:
                info.append(f"Rejected: {esc(', '.join(d.alternatives))}")
            info.append(f"Owner: {esc(names.get(d.owner_id, 'not declared'))}")
            show(f'<div class="bf-muted">{" · ".join(info)}</div>')
            for r in d.source_refs:
                show(quote_block(r))
            if not d.source_refs:
                st.warning("No verified source, so this decision will not be assessed.")
            if d.review_status == ReviewStatus.proposed and st.button("Confirm card", key=f"confirm-{d.id}"):
                orc.confirm_decision(d.id, actor=viewer)
                st.rerun()

# ------------------------------------------------------------------ 2. private check
elif page == PAGES[2]:
    page_header(2, f"Private Check · {names[viewer]}",
                "Questions about decisions you didn't make. Only you can see your answers and feedback.")
    st.info("Scores are practice feedback, not grades. You can answer in English or Italian; "
            "grammar and language never lower the score.", icon="🔒")

    with st.container(border=True):
        others = [d for d in cards.values() if d.owner_id != viewer]
        choice = st.multiselect("Choose up to 2 decisions to be checked on",
                                [d.id for d in others], default=orc.suggest_check_decisions(viewer),
                                max_selections=2, format_func=lambda i: f"{i} · {cards[i].title}")
        if st.button("Get my questions", type="primary"):
            made = orc.start_check(viewer, choice)
            st.success(f"{len(made)} new question(s) below." if made else "No new questions for these decisions.")

    pairs = [(q, ev) for q, ev in orc.my_questions(viewer, viewer) if q.mode != "independent"]
    open_qs = [(q, ev) for q, ev in pairs if ev is None]
    done_qs = [(q, ev) for q, ev in pairs if ev is not None]

    st.subheader(f"To answer ({len(open_qs)})")
    if not open_qs:
        show('<div class="bf-muted">Nothing open. Get new questions above.</div>')
    for q, _ in sorted(open_qs, key=lambda x: x[0].id):
        with st.container(border=True):
            show(f'{pill(q.question_type.value.replace("_", " ").title(), "blue")} '
                 f'<span class="bf-muted">{esc(q.decision_id)} · {esc(cards[q.decision_id].title)}</span>')
            show(f'<div class="bf-question">{esc(q.prompt)}</div>')
            with st.form(f"form-{q.id}"):
                answer = st.text_area("Your answer", key=f"a-{q.id}", height=110)
                if st.form_submit_button("Submit", type="primary"):
                    res = orc.submit_answer(q.id, answer, viewer)
                    if res.blocked:
                        st.warning(res.message)
                    else:
                        st.rerun()

    st.subheader(f"Answered ({len(done_qs)})")
    for q, ev in sorted(done_qs, key=lambda x: x[0].id):
        with st.container(border=True):
            label, kind = EVIDENCE_PILL[ev.status.value]
            show(f'{pill(label, kind)} <span class="bf-muted">{esc(q.decision_id)} · '
                 f'{esc(q.question_type.value.replace("_", " "))}</span>')
            show(f'<div class="bf-title" style="margin:0.4rem 0">{esc(q.prompt)}</div>')
            show(f'<div class="bf-muted">Your answer: {esc(ev.answer)}</div>')
            st.markdown(f"Result: {ev.feedback}")

# ------------------------------------------------------------------ 3. coverage
elif page == PAGES[3]:
    page_header(3, "Team Coverage",
                "How many decisions at least two of you can explain. Only counts are shown, never names or scores.")
    report = orc.team_coverage()
    snaps = orc.coverage_snapshots()
    base = snaps[0] if snaps else None

    start = base or {"numerator": report.numerator, "denominator": report.denominator, "spof": report.spof_decision_ids}
    gained = report.numerator - start["numerator"]
    spof_drop = len(start.get("spof", [])) - len(report.spof_decision_ids)
    stats = [
        ("Before", coverage_text(start["numerator"], start["denominator"]), "when the demo started"),
        ("Now", coverage_text(report.numerator, report.denominator),
         f"<b>+{gained} decision{'s' if gained != 1 else ''}</b> covered" if gained > 0 else "no change yet"),
        ("Single points of failure", str(len(report.spof_decision_ids)),
         f"<b>−{spof_drop}</b> since start" if spof_drop > 0 else "decisions only one person can explain"),
    ]
    tiles = "".join(f'<div><div class="k">{k}</div><div class="v">{v}</div><div class="s">{sub}</div></div>'
                    for k, v, sub in stats)
    show(f'<div class="bf-panel">{ring(report.numerator, report.denominator, start["numerator"])}'
         f'<div class="bf-pstats">{tiles}</div>'
         f'<div class="note">The ring fills as more decisions get a second person who can explain them.</div></div>')

    st.subheader("Decisions")
    team_size = len(members)
    for c in report.per_decision:
        with st.container(border=True):
            label, kind = COVERAGE_PILL[c.status]
            n = len(c.demonstrated_by)
            left, mid, right = st.columns([4.5, 1.6, 1.8])
            left.markdown(f"**{c.decision_id} · {cards[c.decision_id].title}**")
            with mid:
                dots = "".join('<i class="on"></i>' if k < n else "<i></i>" for k in range(team_size))
                show(f'<div class="bf-dots2 {c.status}" title="{n} of {team_size}">{dots}</div>'
                     f'<span class="bf-muted">{n} can explain it</span>')
            with right:
                show(pill(label, kind))

    show('<div class="bf-muted" style="margin-top:0.8rem">Decision Coverage = critical decisions that 2 or more '
         'members can explain ÷ critical decisions that have been assessed. This is a prototype indicator, '
         'not a validated metric. "Not assessed" is never counted as failed.</div>')

# ------------------------------------------------------------------ 4. missions
elif page == PAGES[4]:
    page_header(4, "Teach Each Other",
                "For each decision only one person can explain, a teammate who understands it teaches one who doesn't.")
    if st.button("Find knowledge silos and propose missions", type="primary"):
        orc.propose_missions()
        st.rerun()

    all_missions = orc.missions()
    if not all_missions:
        show('<div class="bf-muted">No missions yet. Press the button above.</div>')
    for m in all_missions:
        involved = viewer in (m.mentor_id, m.learner_id)
        public = m.status in (MissionStatus.accepted, MissionStatus.completed, MissionStatus.verified)
        with st.container(border=True):
            label, kind = MISSION_PILL[m.status.value]
            left, right = st.columns([5, 1.8])
            left.markdown(f"**{m.decision_id} · {cards[m.decision_id].title}**")
            with right:
                show(pill(label, kind))

            if m.status == MissionStatus.fallback:
                st.write(m.fallback_message)
                if involved:
                    show(f'<div class="bf-muted">{esc(explain_mission(m, names))}</div>')
                continue
            if not (involved or public):
                show('<div class="bf-muted">The people in this mission are shown only to them until both accept.</div>')
                continue

            show(flow(m))
            show(f'<div class="bf-muted">{esc(explain_mission(m, names))}</div>')
            st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(m.steps, 1)))

            if involved and m.status == MissionStatus.proposed:
                mine = m.mentor_consent if viewer == m.mentor_id else m.learner_consent
                role = "mentor" if viewer == m.mentor_id else "learner"
                if mine:
                    st.info("You accepted. Waiting for the other person.")
                elif st.button(f"I agree to take part as {role}", key=f"acc-{m.id}", type="primary"):
                    orc.accept_mission(m.id, viewer)
                    st.rerun()

# ------------------------------------------------------------------ 5. retest
elif page == PAGES[5]:
    page_header(5, f"Defense Retest · {names[viewer]}",
                "After the teaching session, answer a new question on your own. No hints are available here.")
    mine = [m for m in orc.missions() if m.learner_id == viewer and m.mentor_id]
    if not mine:
        st.info("You have no teaching mission as a learner.")
    for m in mine:
        with st.container(border=True):
            label, kind = MISSION_PILL[m.status.value]
            left, right = st.columns([5, 1.8])
            left.markdown(f"**{m.decision_id} · {cards[m.decision_id].title}**")
            with right:
                show(pill(label, kind))

            if m.status == MissionStatus.proposed:
                st.write("Both people must accept the mission before the retest.")
                continue
            if m.status == MissionStatus.verified:
                show(win("Transfer verified", f"You explained {m.decision_id} on a new question, with no hints. "
                                              "Team coverage went up."))
                continue
            if st.button("Start a new independent question", key=f"rt-{m.id}"):
                orc.start_retest(m.id, viewer)
                st.rerun()

            m = next(x for x in orc.missions() if x.id == m.id)
            if m.retest_question_id:
                q = next(q for q, _ in orc.my_questions(viewer, viewer) if q.id == m.retest_question_id)
                show(f'<div class="bf-question">{esc(q.prompt)}</div>')
                with st.form(f"retest-{m.id}"):
                    answer = st.text_area("Your answer", height=130)
                    if st.form_submit_button("Submit", type="primary"):
                        res = orc.submit_retest(m.id, answer, viewer)
                        if res.blocked:
                            st.error(res.message)
                        else:
                            cov = coverage_text(res.coverage.numerator, res.coverage.denominator)
                            if res.evidence.rubric_score == 2:
                                show(win("Transfer verified", f"New question passed. Team coverage is now {cov}."))
                            else:
                                label, kind = EVIDENCE_PILL[res.evidence.status.value]
                                show(pill(label, kind))
                            st.markdown(f"Result: {res.evidence.feedback}")
                            st.markdown(f"Mission status: **{res.mission.status.value}** · team coverage now "
                                        f"{coverage_text(res.coverage.numerator, res.coverage.denominator)}")

# ------------------------------------------------------------------ 6. evidence & limits
else:
    page_header(6, "Evidence & Limits", "Where every decision comes from, what the agent did, and what it can't do.")
    log = orc.db.load_log()

    def log_table(events):
        return pd.DataFrame([{"time": e.ts.strftime("%H:%M:%S"), "actor": e.actor, "action": e.action,
                              "detail": str(e.detail)} for e in events])

    sources, actions, abstain, limits = st.tabs(["Sources", "Action log", "Abstentions & blocked", "Limits"])
    with sources:
        st.dataframe(pd.DataFrame([{
            "Decision": d.id, "Status": d.review_status.value,
            "File": ", ".join(r.file for r in d.source_refs) or "none",
            "Page": ", ".join(str(r.page) for r in d.source_refs),
            "Quote": " / ".join(r.quote for r in d.source_refs),
        } for d in cards.values()]), hide_index=True, width="stretch")
    with actions:
        st.caption("Every step the agent takes. Answers and scores are never written here.")
        st.dataframe(log_table(log[::-1]), hide_index=True, width="stretch")
    with abstain:
        flagged = [e for e in log if any(k in e.action for k in ("abstain", "blocked", "answer_request"))
                   or e.detail.get("abstained")]
        if flagged:
            st.dataframe(log_table(flagged), hide_index=True, width="stretch")
        else:
            st.write("None yet.")
    with limits:
        st.markdown(
            "- Scores are practice feedback, not grades. A score from the model can be wrong.\n"
            "- One correct answer shows someone explained one decision on one day, not that they'll remember it.\n"
            "- Decision Coverage is a prototype indicator, not a validated metric.\n"
            "- In demo mode, answers are scored with a keyword list on made-up data, as a stand-in for the model.\n"
            "- No source means no assessment. If nobody can explain a decision, the app points to the TA.\n"
            "- In a small team even totals can identify people, so the team view shows only counts per decision."
        )
