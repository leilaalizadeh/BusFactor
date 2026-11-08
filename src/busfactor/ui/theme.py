"""BusFactor — Intelligence Observatory: design tokens and the single stylesheet.

Rules of the system
- Surfaces: canvas (the app) → panel (primary content) → raised (interactive / elevated), plus an
  `ink` instrument surface that stays dark in both themes (hero and knowledge map).
- Type: IBM Plex Sans (light weights for display and numerals), IBM Plex Sans for UI, IBM Plex Mono only
  for ids and small data labels. Loaded with local() and system fallbacks: no download, works offline.
- Scale: nothing that matters is below 12px. Spacing on a 4px grid. Radii sm/md/lg/pill.
- Colour carries meaning (verified, vulnerable, critical, unassessed, mission, selection) and is always
  paired with text and a glyph.
Styling hooks: Streamlit's public data-testid attributes and the documented `st-key-<key>` classes only.
"""
from __future__ import annotations

TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "canvas": "#07090C", "canvas_glow": "#0C1A26", "panel": "#0E1318", "raised": "#141B23",
        "line": "#1F2831", "line_strong": "#2E3A46",
        "text": "#EEF2F5", "muted": "#A6B0BB", "faint": "#8A95A2",
        "teal": "#2DD4BF", "amber": "#F5A524", "violet": "#A78BFA", "red": "#F87171", "neutral": "#94A3B8",
        "sky": "#7DD3FC", "focus": "#7DD3FC", "on_teal": "#04211D",
        "teal_bg": "rgba(45,212,191,.10)", "amber_bg": "rgba(245,165,36,.10)", "violet_bg": "rgba(167,139,250,.11)",
        "red_bg": "rgba(248,113,113,.10)", "neutral_bg": "rgba(148,163,184,.10)", "sky_bg": "rgba(125,211,252,.10)",
        "shadow": "0 24px 48px -32px rgba(0,0,0,.9)", "shadow_hi": "0 28px 60px -28px rgba(0,0,0,.95)",
    },
    "light": {
        "canvas": "#F2F0EB", "canvas_glow": "#E6EEF2", "panel": "#FFFFFF", "raised": "#F8F6F1",
        "line": "#E3DED5", "line_strong": "#CBC4B8",
        "text": "#0E141A", "muted": "#4A5561", "faint": "#5C6773",
        "teal": "#0F766E", "amber": "#A15C07", "violet": "#6D28D9", "red": "#B91C1C", "neutral": "#475569",
        "sky": "#1D4ED8", "focus": "#1D4ED8", "on_teal": "#FFFFFF",
        "teal_bg": "rgba(15,118,110,.08)", "amber_bg": "rgba(161,92,7,.08)", "violet_bg": "rgba(109,40,217,.07)",
        "red_bg": "rgba(185,28,28,.07)", "neutral_bg": "rgba(71,85,105,.07)", "sky_bg": "rgba(29,78,216,.07)",
        "shadow": "0 20px 44px -34px rgba(40,32,16,.45)", "shadow_hi": "0 26px 56px -30px rgba(40,32,16,.5)",
    },
}
# The instrument surface (hero, knowledge map) is always dark, in both themes.
INK = {"ink": "#080C11", "ink_2": "#0D141C", "ink_line": "#1E2A36", "ink_text": "#EEF2F5", "ink_muted": "#A6B0BB",
       "ink_faint": "#8A95A2"}

FONT_DISPLAY = '"IBM Plex Sans", "Segoe UI Variable Display", "SF Pro Display", "Helvetica Neue", system-ui, sans-serif'
FONT_BODY = '"IBM Plex Sans", "Segoe UI Variable Text", "SF Pro Text", system-ui, -apple-system, "Segoe UI", sans-serif'
FONT_MONO = '"IBM Plex Mono", "Cascadia Mono", "SF Mono", ui-monospace, Consolas, monospace'
SPACE = {"1": "4px", "2": "8px", "3": "12px", "4": "16px", "5": "20px", "6": "24px", "8": "32px", "10": "40px",
         "14": "56px", "18": "72px"}
RADIUS = {"sm": "8px", "md": "14px", "lg": "20px", "pill": "999px"}
MOTION = {"fast": "140ms", "base": "220ms", "slow": "700ms", "ease": "cubic-bezier(.2,.7,.2,1)"}
TYPE = {  # role: font shorthand
    "display": f"300 clamp(2.75rem, 4.5vw, 4.6rem)/1.02 {FONT_DISPLAY}",
    "page": f"300 clamp(2rem, 3vw, 2.75rem)/1.08 {FONT_DISPLAY}",
    "section": f"600 1.2rem/1.3 {FONT_BODY}",
    "card": f"600 1.05rem/1.35 {FONT_BODY}",
    "body": f"400 1rem/1.6 {FONT_BODY}",
    "support": f"400 .9375rem/1.55 {FONT_BODY}",
    "numeral": f"300 clamp(2.4rem, 3.2vw, 3.1rem)/1 {FONT_DISPLAY}",
    "label": f"500 .75rem/1.35 {FONT_MONO}",
    "caption": f"400 .8125rem/1.45 {FONT_BODY}",
}


def palette(theme_type: str | None) -> dict[str, str]:
    return {**TOKENS["light" if theme_type == "light" else "dark"], **INK}


def _vars(prefix: str, values: dict[str, str]) -> str:
    return "".join(f"--{prefix}-{k.replace('_', '-')}:{v};" for k, v in values.items())


def stylesheet(theme_type: str | None) -> str:
    t = palette(theme_type)
    root = (_vars("bf", t) + _vars("sp", SPACE) + _vars("r", RADIUS) + _vars("mo", MOTION) + _vars("type", TYPE)
            + f"--font-display:{FONT_DISPLAY};--font-body:{FONT_BODY};--font-mono:{FONT_MONO};")
    # Instrument surfaces (hero, map) always speak the dark palette: chips, text and lines, in both themes.
    d = TOKENS["dark"]
    ink_vars = "".join(f"--bf-{k.replace('_', '-')}:{d[k]};" for k in (
        "teal", "amber", "violet", "red", "neutral", "sky", "teal_bg", "amber_bg", "violet_bg", "red_bg", "neutral_bg",
        "on_teal", "line_strong"))
    ink_vars += (f"--bf-text:{INK['ink_text']};--bf-muted:{INK['ink_muted']};--bf-faint:{INK['ink_faint']};"
                 f"--bf-line:{INK['ink_line']};--bf-raised:{INK['ink_2']};--bf-panel:{INK['ink']};")
    ink_scope = '[class*="st-key-bfi-"] { ' + ink_vars + " }"
    return f"""<style>
@font-face {{ font-family: "IBM Plex Sans"; src: local("IBM Plex Sans"), local("IBMPlexSans"),
  local("IBM Plex Sans Var"); font-weight: 100 700; font-display: swap; }}
@font-face {{ font-family: "IBM Plex Mono"; src: local("IBM Plex Mono"), local("IBMPlexMono"); font-weight: 400;
  font-display: swap; }}
@font-face {{ font-family: "IBM Plex Mono"; src: local("IBM Plex Mono Medium"), local("IBMPlexMono-Medium");
  font-weight: 500; font-display: swap; }}
:root {{ {root} }}

/* ---------- canvas & shell ---------- */
.stApp {{ background:
    radial-gradient(1200px 520px at 78% -8%, var(--bf-canvas-glow) 0%, transparent 62%),
    var(--bf-canvas); color: var(--bf-text); font-family: var(--font-body); }}
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button {{ font-family: var(--font-body); }}
[data-testid="stMainBlockContainer"] {{ max-width: 1520px; padding: 18px 40px 72px; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbar"], .stAppDeployButton, [data-testid="stDecoration"] {{ display: none !important; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
.stApp h1, .stApp h2, .stApp h3 {{ color: var(--bf-text); font-family: var(--font-body); }}
.stApp h1.bf-display {{ font: var(--type-display) !important; letter-spacing: -.035em; padding: 0 !important;
  margin: 12px 0 18px !important; }}
.stApp p.bf-lede {{ margin: 0 !important; }}
.stApp h1.bf-page, .stApp h2.bf-page {{ font: var(--type-page) !important; letter-spacing: -.028em; padding: 0; }}
.stApp h3 {{ font: var(--type-section) !important; letter-spacing: -.01em; }}
.stApp a {{ color: var(--bf-sky); }}
.stApp :focus-visible {{ outline: 2px solid var(--bf-focus) !important; outline-offset: 3px; border-radius: 6px; }}
[data-testid="stVerticalBlock"] {{ gap: var(--sp-4); }}

/* ---------- top bar ---------- */
.st-key-bf-topbar {{ padding: 6px 0 14px; border-bottom: 1px solid var(--bf-line); margin-bottom: 4px; }}
.st-key-bf-topbar [data-testid="stWidgetLabel"] p {{ font: var(--type-label); letter-spacing: .1em;
  text-transform: uppercase; color: var(--bf-faint); }}
.st-key-nav {{ margin: 2px 0 22px; }}
.st-key-nav [role="radiogroup"] {{ gap: 4px; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none;
  border-bottom: 1px solid var(--bf-line); padding-bottom: 0; }}
.st-key-nav [role="radiogroup"]::-webkit-scrollbar {{ display: none; }}
.st-key-nav [role="radiogroup"] label {{ padding: 10px 14px 12px; margin: 0; border-bottom: 2px solid transparent;
  border-radius: 0; white-space: nowrap; transition: color var(--mo-fast) ease, border-color var(--mo-base) ease;
  cursor: pointer; }}
.st-key-nav [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
.st-key-nav [role="radiogroup"] label p {{ font: 500 .95rem/1 var(--font-body); color: var(--bf-muted); }}
.st-key-nav [role="radiogroup"] label:hover p {{ color: var(--bf-text); }}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] {{ border-bottom-color: var(--bf-teal); }}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p {{ color: var(--bf-text); font-weight: 600; }}
.st-key-nav [role="radiogroup"] label:has(input:focus-visible) {{ outline: 2px solid var(--bf-focus); outline-offset: -2px; }}

/* ---------- panels (st.container(key="bfc-...")) ---------- */
[class*="st-key-bfc-"] {{ background: var(--bf-panel); border: 1px solid var(--bf-line); border-radius: var(--r-lg);
  padding: 22px 24px; box-shadow: var(--bf-shadow); transition: border-color var(--mo-base) ease, box-shadow var(--mo-base) ease; }}
[class*="st-key-bfc-"]:hover {{ border-color: var(--bf-line-strong); }}
[class*="st-key-bfc-focus"] {{ border-color: var(--bf-sky); box-shadow: 0 0 0 1px var(--bf-sky), var(--bf-shadow-hi); }}
[class*="st-key-bfi-"] {{ background: linear-gradient(160deg, var(--bf-ink-2), var(--bf-ink) 60%); color: var(--bf-ink-text);
  border: 1px solid var(--bf-ink-line); border-radius: var(--r-lg); padding: 30px 34px; box-shadow: var(--bf-shadow-hi);
  position: relative; overflow: hidden; }}
[class*="st-key-bfi-"]::before {{ content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .5;
  background-image: linear-gradient(var(--bf-ink-line) 1px, transparent 1px), linear-gradient(90deg, var(--bf-ink-line) 1px, transparent 1px);
  background-size: 48px 48px; mask-image: radial-gradient(ellipse at 70% 40%, #000 0%, transparent 70%); }}
[class*="st-key-bfi-"] p, [class*="st-key-bfi-"] span {{ color: var(--bf-ink-text); }}
{ink_scope}
[class*="st-key-bfr-"] {{ border-bottom: 1px solid var(--bf-line); padding: 14px 4px; transition: background var(--mo-fast) ease;
  border-radius: var(--r-sm); }}
[class*="st-key-bfr-"]:hover {{ background: var(--bf-raised); }}
[class*="st-key-bfr-"]:last-child {{ border-bottom: none; }}

/* ---------- controls ---------- */
.stButton button, .stFormSubmitButton button, [data-testid="stPopover"] button {{ border-radius: var(--r-pill);
  font: 500 .9rem/1 var(--font-body); padding: 10px 18px; min-height: 40px; border: 1px solid var(--bf-line-strong);
  background: var(--bf-raised); color: var(--bf-text); transition: all var(--mo-fast) ease; }}
.stButton button:hover, .stFormSubmitButton button:hover, [data-testid="stPopover"] button:hover {{
  border-color: var(--bf-text); color: var(--bf-text); background: var(--bf-raised); }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{ background: var(--bf-teal) !important;
  color: var(--bf-on-teal) !important; border-color: transparent !important; font-weight: 600 !important; }}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{ filter: brightness(1.08); }}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p {{ color: var(--bf-on-teal) !important; }}
.stButton button:disabled {{ opacity: .45; }}
[class*="st-key-bfi-"] .stButton button:not([data-testid="stBaseButton-primary"]) {{ background: transparent;
  color: var(--bf-ink-text); border-color: var(--bf-ink-line); }}
.stTextInput input, .stTextArea textarea, .stNumberInput input {{ background: var(--bf-raised) !important;
  color: var(--bf-text) !important; border-radius: var(--r-sm); font: var(--type-body); }}
.stTextArea textarea {{ min-height: 140px; line-height: 1.6; }}
[data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div,
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"] {{
  background: var(--bf-raised) !important; border: 1px solid var(--bf-line-strong) !important;
  border-radius: var(--r-sm) !important; color: var(--bf-text) !important; }}
[data-testid="stSelectbox"] > div > div:focus-within, [data-testid="stMultiSelect"] > div > div:focus-within,
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within {{
  border-color: var(--bf-focus) !important; box-shadow: 0 0 0 3px var(--bf-sky-bg); }}
[data-testid="stSelectbox"] *, [data-testid="stMultiSelect"] input {{ color: var(--bf-text); }}
[data-baseweb="popover"] ul, [data-baseweb="menu"] {{ background: var(--bf-raised) !important; }}
[data-testid="stMultiSelect"] span[data-tag] {{ background: var(--bf-teal-bg) !important; border: 1px solid var(--bf-teal);
  color: var(--bf-text) !important; border-radius: var(--r-pill) !important; }}
[data-testid="stMultiSelect"] span[data-tag] * {{ color: var(--bf-text) !important; fill: var(--bf-text); }}
[data-testid="stWidgetLabel"] p {{ font: 500 .875rem/1.4 var(--font-body); color: var(--bf-muted); }}
[data-testid="stExpander"] details {{ background: var(--bf-panel); border: 1px solid var(--bf-line); border-radius: var(--r-md); }}
[data-testid="stExpander"] summary p {{ font: 500 .95rem/1.3 var(--font-body); }}
[data-testid="stAlert"] {{ border-radius: var(--r-md); }}
[data-testid="stAlert"] > div {{ background: var(--bf-sky-bg) !important; border: 1px solid var(--bf-sky);
  border-radius: var(--r-md); color: var(--bf-text) !important; }}
[data-testid="stAlert"] p, [data-testid="stAlert"] strong {{ color: var(--bf-text) !important; }}
[data-testid="stAlertContentWarning"] {{ border-color: var(--bf-amber) !important; }}
[data-testid="stAlertContentError"] {{ border-color: var(--bf-red) !important; }}
[data-testid="stForm"] {{ border: 1px solid var(--bf-line); border-radius: var(--r-md); padding: 18px; background: var(--bf-panel); }}
[data-testid="stButtonGroup"] button {{ border-radius: var(--r-pill) !important; font: 500 .875rem/1 var(--font-body); }}
[data-testid="stButtonGroup"] {{ flex-wrap: wrap; }}
[data-testid="stTab"] p {{ font: 500 .95rem/1 var(--font-body); color: var(--bf-muted) !important; }}
[data-testid="stTab"]:hover p, [data-testid="stTab"][data-selected="true"] p {{ color: var(--bf-text) !important; }}
[data-testid="stTab"][data-selected="true"] p {{ font-weight: 600; }}
[data-testid="stCaptionContainer"] p {{ color: var(--bf-faint); font: var(--type-caption); }}
[data-testid="stCheckbox"] label p {{ color: var(--bf-text); }}

/* ---------- typography roles ---------- */
.bf-label {{ font: var(--type-label); letter-spacing: .12em; text-transform: uppercase; color: var(--bf-faint); }}
.bf-display {{ font: var(--type-display); letter-spacing: -.035em; margin: 14px 0 16px; color: var(--bf-ink-text); }}
.bf-display .accent {{ background: linear-gradient(92deg, var(--bf-teal), #8BE9DA 55%, var(--bf-sky));
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
.bf-page {{ font: var(--type-page); letter-spacing: -.028em; margin: 10px 0 10px; color: var(--bf-text); }}
.bf-page .accent {{ color: var(--bf-teal); }}
.bf-lede {{ font: 400 1.0625rem/1.6 var(--font-body); color: var(--bf-muted); max-width: 46rem; margin: 0; }}
.bf-section {{ font: var(--type-section); margin: 0; color: var(--bf-text); letter-spacing: -.01em; }}
.bf-card-title {{ font: var(--type-card); margin: 0; color: var(--bf-text); }}
.stApp .bf-spot-title {{ font: 300 clamp(1.6rem, 2vw, 2rem)/1.15 var(--font-display) !important; letter-spacing: -.02em;
  margin: 10px 0 14px !important; padding: 0 !important; color: var(--bf-text); }}
.stApp p.bf-result {{ font: var(--type-support); color: var(--bf-text); margin: 6px 0 0; }}
.bf-support {{ font: var(--type-support); color: var(--bf-muted); margin: 0; }}
.bf-numeral {{ font: var(--type-numeral); letter-spacing: -.03em; font-variant-numeric: tabular-nums; color: var(--bf-text); }}
.bf-numeral small {{ font: 400 1.05rem/1 var(--font-body); color: var(--bf-muted); margin-left: 6px; letter-spacing: 0; }}
.bf-mono {{ font-family: var(--font-mono); }}
.bf-head {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; flex-wrap: wrap; margin: 6px 0 22px; }}
.bf-head-stats {{ display: flex; gap: 28px; }}
.bf-head-stats div {{ text-align: right; }}
.bf-head-stats b {{ display: block; font: 300 2rem/1 var(--font-display); color: var(--bf-text); font-variant-numeric: tabular-nums; }}

/* ---------- status chips: glyph + text ---------- */
.bf-chip {{ display: inline-flex; align-items: center; gap: 7px; padding: 4px 11px 4px 9px; border-radius: var(--r-pill);
  font: 500 .8125rem/1.3 var(--font-body); white-space: nowrap; border: 1px solid currentColor; }}
.bf-chip b {{ font: 600 .8rem/1 var(--font-mono); }}
.bf-teal {{ color: var(--bf-teal); background: var(--bf-teal-bg); }} .bf-amber {{ color: var(--bf-amber); background: var(--bf-amber-bg); }}
.bf-violet {{ color: var(--bf-violet); background: var(--bf-violet-bg); }} .bf-red {{ color: var(--bf-red); background: var(--bf-red-bg); }}
.bf-neutral {{ color: var(--bf-neutral); background: var(--bf-neutral-bg); }} .bf-sky {{ color: var(--bf-sky); background: var(--bf-sky-bg); }}
.bf-chips {{ display: flex; gap: 8px; flex-wrap: wrap; }}

/* ---------- brand ---------- */
.bf-brand {{ display: flex; align-items: center; gap: 12px; min-height: 44px; }}
.bf-brand svg {{ flex: none; }}
.bf-brand b {{ display: block; font: 600 1.1rem/1.1 var(--font-body); letter-spacing: -.01em; color: var(--bf-text); }}
.bf-brand span {{ display: block; font: var(--type-label); letter-spacing: .14em; color: var(--bf-faint); margin-top: 3px; }}
.bf-demo {{ display: inline-flex; gap: 6px; align-items: center; font: 600 .75rem/1 var(--font-mono); letter-spacing: .1em;
  color: var(--bf-amber); border: 1px solid var(--bf-amber); border-radius: var(--r-pill); padding: 6px 10px; margin-top: 8px; }}

/* ---------- metric cards (one grid row = equal heights) ---------- */
.bf-metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: 8px 0 18px; }}
.bf-metric {{ background: var(--bf-panel); border: 1px solid var(--bf-line); border-radius: var(--r-lg); padding: 20px 22px;
  display: flex; flex-direction: column; gap: 10px; box-shadow: var(--bf-shadow); min-height: 210px;
  transition: border-color var(--mo-base) ease, transform var(--mo-base) var(--mo-ease); }}
.bf-metric:hover {{ border-color: var(--bf-line-strong); transform: translateY(-2px); }}
.bf-metric .top {{ display: flex; justify-content: space-between; align-items: center; }}
.bf-metric .viz {{ margin-top: auto; }}
.bf-metric p {{ margin: 0; }}
.bf-segs {{ display: flex; gap: 4px; height: 8px; }}
.bf-segs i {{ flex: 1; border-radius: 3px; background: var(--bf-line-strong); }}
.bf-segs i.teal {{ background: var(--bf-teal); }} .bf-segs i.amber {{ background: var(--bf-amber); }}
.bf-segs i.red {{ background: var(--bf-red); }} .bf-segs i.violet {{ background: var(--bf-violet); }}
.bf-segs i.neutral {{ background: var(--bf-neutral); }} .bf-segs i.sky {{ background: var(--bf-sky); }}
.st-key-bfc-move {{ background: linear-gradient(150deg, var(--bf-teal-bg), transparent 55%), var(--bf-panel);
  border-color: color-mix(in srgb, var(--bf-teal) 45%, var(--bf-line)); }}
.st-key-bfc-queue .stButton button {{ justify-content: flex-start; text-align: left; border-radius: var(--r-md);
  padding: 14px 16px; min-height: 52px; white-space: normal; line-height: 1.35; }}
.st-key-bfc-queue .stButton button p {{ text-align: left; }}
.st-key-bfi-map {{ padding: 14px 16px; }}
.bf-legend {{ display: flex; gap: 14px; flex-wrap: wrap; font: var(--type-caption); color: var(--bf-muted); margin-top: 8px; }}

/* ---------- hero ---------- */
.bf-hero-facts {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 22px 0 6px; }}
.bf-hero-facts .bf-chip {{ background: rgba(255,255,255,.03); }}
.bf-orbit svg {{ width: 100%; max-width: 470px; height: auto; display: block; margin: 0 auto; }}
.bf-orbit .arc {{ animation: bf-draw var(--mo-slow) var(--mo-ease) both; }}
@keyframes bf-draw {{ from {{ stroke-dashoffset: var(--len); }} }}

/* ---------- vulnerability explorer ---------- */
.bf-vrow-num {{ white-space: nowrap; font: 300 1.65rem/1 var(--font-display); color: var(--bf-faint); font-variant-numeric: tabular-nums; }}
.bf-vrow-title {{ font: var(--type-card); color: var(--bf-text); margin: 6px 0 4px; }}
.bf-dots {{ display: flex; gap: 5px; align-items: center; }}
.bf-dots i {{ width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid var(--bf-line-strong); }}
.bf-dots i.on {{ border-color: currentColor; background: currentColor; }}

/* ---------- next move ---------- */
.bf-move-icon {{ width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center;
  background: var(--bf-teal-bg); border: 1px solid var(--bf-teal); color: var(--bf-teal); margin-bottom: 14px; }}

/* ---------- stepper (missions, setup) ---------- */
.bf-stepper {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); list-style: none; padding: 0;
  margin: 14px 0 6px; counter-reset: s; }}
.bf-stepper li {{ position: relative; padding: 30px 8px 0 0; font: 500 .875rem/1.35 var(--font-body); color: var(--bf-faint); }}
.bf-stepper li::before {{ content: ""; position: absolute; top: 9px; left: 0; right: 0; height: 2px; background: var(--bf-line-strong); }}
.bf-stepper li::after {{ content: ""; position: absolute; top: 3px; left: 0; width: 14px; height: 14px; border-radius: 50%;
  background: var(--bf-panel); border: 2px solid var(--bf-line-strong); }}
.bf-stepper li.done {{ color: var(--bf-text); }} .bf-stepper li.done::before {{ background: var(--bf-teal); }}
.bf-stepper li.done::after {{ background: var(--bf-teal); border-color: var(--bf-teal); }}
.bf-stepper li.now {{ color: var(--bf-text); font-weight: 600; }}
.bf-stepper li.now::after {{ border-color: var(--bf-violet); box-shadow: 0 0 0 4px var(--bf-violet-bg); }}
.bf-stepper li b {{ display: block; font: var(--type-label); letter-spacing: .1em; text-transform: uppercase; margin-bottom: 3px; }}
.bf-stepper li.done b {{ color: var(--bf-teal); }} .bf-stepper li.now b {{ color: var(--bf-violet); }}

/* ---------- evidence, questions, feed, tables, empty ---------- */
.bf-quote {{ margin: 12px 0; padding: 14px 16px 12px 18px; border-left: 2px solid var(--bf-teal); background: var(--bf-raised);
  border-radius: 0 var(--r-sm) var(--r-sm) 0; font: italic 400 1rem/1.6 var(--font-body); color: var(--bf-text); }}
.bf-quote span {{ display: block; margin-top: 8px; font: var(--type-label); font-style: normal; color: var(--bf-faint); }}
.bf-alts {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 2px; }}
.bf-alts span {{ font: 400 .8125rem/1.3 var(--font-body); padding: 4px 10px; border-radius: var(--r-pill);
  border: 1px dashed var(--bf-line-strong); color: var(--bf-muted); text-decoration: line-through; }}
.stApp p.bf-question, .bf-question {{ font: 300 clamp(1.4rem, 2.2vw, 1.85rem)/1.38 var(--font-display) !important; color: var(--bf-text); margin: 14px 0 18px;
  letter-spacing: -.01em; }}
.bf-scenario {{ display: inline-flex; gap: 8px; font: 500 .875rem/1.4 var(--font-body); color: var(--bf-violet);
  background: var(--bf-violet-bg); border: 1px solid var(--bf-violet); padding: 6px 12px; border-radius: var(--r-sm); }}
.bf-feed {{ list-style: none; padding: 0; margin: 4px 0 0; }}
.bf-feed li {{ display: grid; grid-template-columns: 14px 1fr; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--bf-line);
  font: var(--type-support); color: var(--bf-text); }}
.bf-feed li:last-child {{ border-bottom: none; }}
.bf-feed .dot {{ width: 8px; height: 8px; border-radius: 50%; margin-top: 8px; background: var(--bf-neutral); }}
.bf-feed .dot.teal {{ background: var(--bf-teal); }} .bf-feed .dot.violet {{ background: var(--bf-violet); }}
.bf-table {{ width: 100%; border-collapse: collapse; font: var(--type-support); border: none !important; }}
.stApp .bf-table th, .stApp .bf-table td {{ border: none !important; border-bottom: 1px solid var(--bf-line) !important; }}
.stApp .bf-table th {{ border-bottom-color: var(--bf-line-strong) !important; background: transparent !important; }}
.stApp .bf-table tr:hover td {{ background: var(--bf-raised); }}
.bf-table th {{ text-align: left; font: var(--type-label); letter-spacing: .1em; text-transform: uppercase; color: var(--bf-faint);
  padding: 10px 12px; border-bottom: 1px solid var(--bf-line-strong); }}
.bf-table td {{ padding: 12px; border-bottom: 1px solid var(--bf-line); color: var(--bf-text); vertical-align: top; }}
.bf-table td.mono {{ font: 400 .8125rem/1.5 var(--font-mono); color: var(--bf-muted); }}
.bf-empty {{ text-align: center; padding: 28px 20px; border: 1px dashed var(--bf-line-strong); border-radius: var(--r-md); }}
.bf-empty svg {{ width: 56px; height: 56px; color: var(--bf-faint); margin-bottom: 10px; }}
.bf-empty b {{ display: block; font: var(--type-card); color: var(--bf-text); margin-bottom: 4px; }}
.bf-empty span {{ font: var(--type-support); color: var(--bf-muted); }}
.bf-statusbar {{ display: flex; gap: 22px; flex-wrap: wrap; margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--bf-line);
  font: var(--type-label); letter-spacing: .08em; color: var(--bf-faint); text-transform: uppercase; }}
.bf-statusbar i {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--bf-teal); margin-right: 7px; }}
.bf-reveal {{ animation: bf-rise .5s var(--mo-ease) both; }}
@keyframes bf-rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}

/* ---------- responsive ---------- */
/* designed headings: hide Streamlit's anchor-link element, which otherwise adds an invisible line */
.stApp h1.bf-display [data-testid="stHeaderActionElements"], .stApp .bf-page [data-testid="stHeaderActionElements"],
.stApp h3.bf-section [data-testid="stHeaderActionElements"] {{ display: none; }}
@media (max-width: 1100px) {{
  /* page layouts (containers keyed bfx-… and the hero) stack; nested rows keep their own columns */
  :is([class*="st-key-bfx-"], .st-key-bfi-hero) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
    flex-wrap: wrap; row-gap: 18px; }}
  :is([class*="st-key-bfx-"], .st-key-bfi-hero) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important; }}
  .st-key-bf-topbar > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; row-gap: 18px; }}
  .st-key-bf-topbar > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 240px !important; min-width: 220px !important; }}
}}
@media (max-width: 1180px) {{ .bf-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
@media (max-width: 900px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 14px 22px 56px; }}
  [class*="st-key-bfi-"] {{ padding: 24px 22px; }}
}}
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 10px 14px 48px; }}
  .bf-metrics {{ grid-template-columns: minmax(0, 1fr); }}
  .bf-metric {{ min-height: 0; }}
  [class*="st-key-bfc-"] {{ padding: 18px; }}
  .bf-stepper {{ grid-auto-flow: row; }}
  .bf-stepper li {{ padding: 0 0 12px 26px; }}
  .bf-stepper li::before {{ top: 0; bottom: 0; left: 6px; right: auto; width: 2px; height: auto; }}
  .bf-head-stats {{ gap: 18px; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .stApp *, .stApp *::before, .stApp *::after {{ animation: none !important; transition: none !important; }}
}}
</style>"""
