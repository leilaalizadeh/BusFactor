"""HTML/SVG building blocks of the Intelligence Observatory. Every value is escaped; status = glyph + text + tone.

Nothing here invents data: every visual takes real counts from the view models.
"""
from __future__ import annotations

import html
import math
from typing import Iterable

from busfactor.ui.model import EVIDENCE, KNOWLEDGE, MISSION

TONE = {"covered": "teal", "single_point_of_failure": "amber", "no_explainer": "red", "not_assessed": "neutral",
        "unconfirmed": "neutral"}


def esc(text: object) -> str:
    return html.escape(str(text))


# ------------------------------------------------------------------ chips and labels

def chip(label: str, tone: str, glyph: str = "", title: str = "") -> str:
    tip = f' title="{esc(title)}"' if title else ""
    return f'<span class="bf-chip bf-{tone}"{tip}><b aria-hidden="true">{esc(glyph)}</b>{esc(label)}</span>'


def knowledge_chip(state: str) -> str:
    return chip(*KNOWLEDGE[state])


def mission_chip(state: str) -> str:
    return chip(*MISSION[state])


def evidence_chip(status: str) -> str:
    return chip(*EVIDENCE[status])


def label(text: str) -> str:
    return f'<div class="bf-label">{esc(text)}</div>'


eyebrow = label  # kept for older call sites


def page_head(eyebrow_text: str, title_html: str, lede: str, stats: Iterable[tuple[str, str]] = ()) -> str:
    """Page heading: label, light display title, lede; optional right-aligned key numbers (value, label)."""
    right = "".join(f'<div><b>{esc(v)}</b><span class="bf-label">{esc(k)}</span></div>' for v, k in stats)
    return (f'<header class="bf-head bf-reveal"><div>{label(eyebrow_text)}<h1 class="bf-page">{title_html}</h1>'
            f'<p class="bf-lede">{esc(lede)}</p></div>'
            + (f'<div class="bf-head-stats" aria-label="Key numbers">{right}</div>' if right else "") + "</header>")


# ------------------------------------------------------------------ identity

_MARK = """<svg width="38" height="38" viewBox="0 0 38 38" aria-hidden="true">
<circle cx="19" cy="19" r="17.5" fill="none" stroke="currentColor" stroke-opacity=".28"/>
<circle cx="19" cy="19" r="11" fill="none" stroke="currentColor" stroke-opacity=".5" stroke-dasharray="2 3"/>
<circle cx="19" cy="19" r="4" fill="#2DD4BF"/>
<circle cx="19" cy="1.5" r="2.4" fill="currentColor"/><circle cx="34.2" cy="27.8" r="2.4" fill="#F5A524"/>
<circle cx="3.8" cy="27.8" r="2.4" fill="currentColor"/></svg>"""


def brand(badge_text: str | None) -> str:
    """Logo, name, and the orchestrator's own synthetic-data badge text (shown in capitals by CSS)."""
    badge = (f'<div class="bf-demo" style="text-transform:uppercase" title="Fictional project, members, answers and '
             f'consent">● {esc(badge_text)}</div>') if badge_text else ""
    return (f'<div class="bf-brand" style="color:var(--bf-text)">{_MARK}<div><b>BusFactor</b>'
            f'<span>INTELLIGENCE OBSERVATORY</span></div></div>{badge}')


# ------------------------------------------------------------------ small visualizations

def segs(tones: list[str], label_text: str) -> str:
    """One segment per item, coloured by its tone (a count-only bar)."""
    if not tones:
        return '<div class="bf-segs" role="img" aria-label="Nothing to show yet"><i></i></div>'
    return (f'<div class="bf-segs" role="img" aria-label="{esc(label_text)}">'
            + "".join(f'<i class="{t}"></i>' for t in tones) + "</div>")


def dots(on: int, total: int, tone: str) -> str:
    """Members who can explain a decision, as a count: filled dots out of the team size."""
    total = max(total, 1)
    cells = "".join('<i class="on"></i>' if k < on else "<i></i>" for k in range(min(total, 10)))
    return (f'<div class="bf-dots bf-{tone}" style="background:none;border:none" role="img" '
            f'aria-label="{on} of {total} members can explain it">{cells}</div>')


def metric(label_text: str, value_html: str, explanation: str, viz: str, chip_html: str = "") -> str:
    return (f'<article class="bf-metric"><div class="top">{label(label_text)}{chip_html}</div>'
            f'<div class="bf-numeral">{value_html}</div><p class="bf-support">{esc(explanation)}</p>'
            f'<div class="viz">{viz}</div></article>')


def _arc(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    """SVG arc path from angle a0 to a1 (degrees, 0 = top, clockwise)."""
    p = lambda a: (cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))  # noqa: E731
    (x0, y0), (x1, y1) = p(a0), p(a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f}"


def orbit_svg(decisions: list[tuple[str, str, int]], team: int, covered: int, assessed: int, confirmed: int,
              p: dict[str, str]) -> str:
    """Resilience Orbit: the hero instrument, drawn only from real counts.

    decisions: (label, state, explainers) per decision — outer ring, one segment each.
    Inner arcs: verified coverage (covered/assessed) and assessment completeness (assessed/confirmed).
    """
    c, n = 280, len(decisions)
    tone = {"covered": p["teal"], "single_point_of_failure": p["amber"], "no_explainer": p["red"],
            "not_assessed": p["neutral"], "unconfirmed": p["neutral"]}
    dashed = ' stroke-dasharray="2 6"'
    out = [f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{p["ink_line"]}" stroke-width="1"'
           f'{dashed if r in (110, 250) else ""}/>' for r in (110, 186, 250)]
    for k in range(72):  # instrument ticks
        a = math.radians(k * 5)
        r0, r1 = (258, 270) if k % 6 == 0 else (262, 268)
        out.append(f'<line x1="{c + r0 * math.sin(a):.1f}" y1="{c - r0 * math.cos(a):.1f}" x2="{c + r1 * math.sin(a):.1f}" '
                   f'y2="{c - r1 * math.cos(a):.1f}" stroke="{p["ink_line"]}" stroke-width="{1.6 if k % 6 == 0 else 1}"/>')
    if n:
        span, gap = 360 / n, min(6, 90 / n)
        for i, (lbl, state, explainers) in enumerate(decisions):
            a0, a1 = i * span + gap / 2, (i + 1) * span - gap / 2
            dash = ' stroke-dasharray="4 5"' if state == "unconfirmed" else ""
            out.append(f'<path d="{_arc(c, c, 222, a0, a1)}" fill="none" stroke="{tone[state]}" stroke-width="16" '
                       f'stroke-linecap="butt"{dash} opacity=".95"><title>{esc(lbl)}: {esc(KNOWLEDGE[state][0])}, '
                       f'{explainers} of {team} members can explain it</title></path>')
            mid = math.radians((a0 + a1) / 2)
            for k in range(min(team, 8)):  # count of members who can explain it, inside the segment
                ak = mid + math.radians((k - (min(team, 8) - 1) / 2) * 4.2)
                fill = tone[state] if k < explainers else "none"
                out.append(f'<circle cx="{c + 198 * math.sin(ak):.1f}" cy="{c - 198 * math.cos(ak):.1f}" r="3.2" '
                           f'fill="{fill}" stroke="{tone[state]}" stroke-width="1.2"/>')
            lx, ly = c + 246 * math.sin(mid), c - 246 * math.cos(mid) + 5
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-family="IBM Plex Mono, Consolas, monospace" '
                       f'font-size="13" font-weight="500" fill="{p["ink_text"]}" paint-order="stroke" '
                       f'stroke="{p["ink"]}" stroke-width="4">{esc(lbl)} {esc(KNOWLEDGE[state][2])}</text>')

    def ring(r: float, frac: float, colour: str, width: float) -> str:
        length = 2 * math.pi * r
        track = f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{p["ink_line"]}" stroke-width="{width}"/>'
        if frac <= 0:
            return track
        if frac >= 1:
            arc = (f'<circle class="arc" cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{colour}" stroke-width="{width}" '
                   f'style="--len:{length:.1f}" stroke-dasharray="{length:.1f}" stroke-dashoffset="0" '
                   f'transform="rotate(-90 {c} {c})"/>')
        else:
            seg = length * frac
            arc = (f'<path class="arc" d="{_arc(c, c, r, 0, 360 * frac)}" fill="none" stroke="{colour}" '
                   f'stroke-width="{width}" stroke-linecap="round" style="--len:{seg:.1f}" '
                   f'stroke-dasharray="{seg:.1f}" stroke-dashoffset="0"/>')
        return track + arc

    out.append(ring(160, covered / assessed if assessed else 0, p["teal"], 10))
    out.append(ring(138, assessed / confirmed if confirmed else 0, p["sky"], 5))
    big = f"{covered}/{assessed}" if assessed else "—"
    sub = f"{covered / assessed:.0%} of assessed decisions" if assessed else "nothing assessed yet"
    out.append(f'<text x="{c}" y="{c + 6}" text-anchor="middle" font-family="IBM Plex Sans, Segoe UI, sans-serif" '
               f'font-size="76" font-weight="300" fill="{p["ink_text"]}" letter-spacing="-2">{esc(big)}</text>')
    out.append(f'<text x="{c}" y="{c + 38}" text-anchor="middle" font-family="IBM Plex Mono, Consolas, monospace" '
               f'font-size="12.5" font-weight="500" letter-spacing="2" fill="{p["teal"]}">VERIFIED COVERAGE</text>')
    out.append(f'<text x="{c}" y="{c + 60}" text-anchor="middle" font-family="IBM Plex Sans, Segoe UI, sans-serif" '
               f'font-size="14" fill="{p["ink_muted"]}">{esc(sub)}</text>')
    summary = (f"Resilience orbit: {covered} of {assessed} assessed decisions are shared; {assessed} of {confirmed} "
               "confirmed decisions are assessed. " + "; ".join(f"{lbl} {KNOWLEDGE[s][0]}" for lbl, s, _ in decisions))
    return (f'<figure class="bf-orbit" style="margin:0"><svg viewBox="0 0 560 560" role="img" aria-label="{esc(summary)}">'
            + "".join(out) + "</svg></figure>")


def pulse_svg(points: list[tuple[str, int, int]], p: dict[str, str]) -> str:
    """Resilience Pulse trend (only for two or more stored observations)."""
    w, h, padx, top, bottom = 560, 210, 30, 34, 40
    peak = max(max(den for _, _, den in points), 1)
    n = len(points)
    xs = [padx + (w - 2 * padx) * i / (n - 1) for i in range(n)]
    ys = [h - bottom - (h - top - bottom) * num / peak for _, num, _ in points]
    line = f"M{xs[0]:.1f},{ys[0]:.1f}" + "".join(f" H{xs[i]:.1f} V{ys[i]:.1f}" for i in range(1, n))
    area = line + f" V{h - bottom} H{xs[0]:.1f} Z"
    grid = "".join(f'<line x1="{padx}" x2="{w - padx}" y1="{h - bottom - (h - top - bottom) * k / peak:.1f}" '
                   f'y2="{h - bottom - (h - top - bottom) * k / peak:.1f}" stroke="{p["line"]}" stroke-dasharray="2 5"/>'
                   for k in range(peak + 1))
    marks = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{6 if i == n - 1 else 4.5}" fill="{p["panel"]}" stroke="{p["teal"]}" '
        f'stroke-width="2.5"/><text x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" font-size="15" font-weight="600" '
        f'fill="{p["text"]}">{num}/{den}</text><text x="{x:.1f}" y="{h - 14}" text-anchor="middle" font-size="13" '
        f'fill="{p["muted"]}">{esc(lbl)}</text>'
        for i, (x, y, (lbl, num, den)) in enumerate(zip(xs, ys, points)))
    summary = "; ".join(f"{lbl}: {num} of {den} covered" for lbl, num, den in points)
    return (f'<figure style="margin:0" aria-label="Resilience Pulse. {esc(summary)}"><svg viewBox="0 0 {w} {h}" '
            f'role="img" style="width:100%;height:auto"><defs><linearGradient id="bfpulse" x1="0" x2="0" y1="0" y2="1">'
            f'<stop offset="0" stop-color="{p["teal"]}" stop-opacity=".28"/><stop offset="1" stop-color="{p["teal"]}" '
            f'stop-opacity="0"/></linearGradient></defs>{grid}<path d="{area}" fill="url(#bfpulse)"/>'
            f'<path d="{line}" fill="none" stroke="{p["teal"]}" stroke-width="3" stroke-linejoin="round"/>{marks}</svg></figure>')


# ------------------------------------------------------------------ structure

def stepper(stages: list[tuple[str, str]], aria: str = "Progress") -> str:
    words = {"done": "Done", "now": "Now", "todo": "Next"}
    items = "".join(f'<li class="{state}"><b>{i:02d} · {words[state]}</b>{esc(text)}</li>'
                    for i, (text, state) in enumerate(stages, 1))
    return f'<ol class="bf-stepper" aria-label="{esc(aria)}">{items}</ol>'


stage_track = stepper  # older call sites


def quote(ref) -> str:
    where = f"{ref.file} · page {ref.page}" + (f" · {ref.section}" if ref.section else "")
    return f'<blockquote class="bf-quote">“{esc(ref.quote)}”<span>{esc(where)}</span></blockquote>'


def alternatives(items: list[str]) -> str:
    if not items:
        return ""
    return ('<div class="bf-alts" aria-label="Rejected alternatives">'
            + "".join(f"<span>{esc(a)}</span>" for a in items) + "</div>")


_ART = """<svg viewBox="0 0 64 64" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4">
<circle cx="32" cy="32" r="26" stroke-dasharray="2 4"/><circle cx="32" cy="32" r="5"/><circle cx="32" cy="6" r="3"/>
<circle cx="54.5" cy="45" r="3"/><circle cx="9.5" cy="45" r="3"/></svg>"""


def empty(title: str, text: str) -> str:
    return f'<div class="bf-empty" role="status">{_ART}<b>{esc(title)}</b><span>{esc(text)}</span></div>'


def feed_html(items: list[tuple[str, str]]) -> str:
    if not items:
        return empty("No shared progress yet", "Confirmed decisions, accepted missions and coverage changes appear here.")
    rows = "".join(f'<li><span class="dot {tone}" aria-hidden="true"></span><span>{esc(text)}</span></li>'
                   for tone, text in items)
    return f'<ul class="bf-feed" aria-label="Recent team progress">{rows}</ul>'


def table(headers: list[str], rows: list[list[str]], mono: Iterable[int] = (), caption: str = "") -> str:
    """An accessible HTML table (themed in light and dark, unlike Streamlit's canvas grid)."""
    mono = set(mono)
    head = "".join(f'<th scope="col">{esc(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f'<td{" class=mono" if i in mono else ""}>{esc(v)}</td>' for i, v in enumerate(r))
                   + "</tr>" for r in rows)
    cap = f'<caption class="bf-label" style="text-align:left;padding-bottom:8px">{esc(caption)}</caption>' if caption else ""
    return f'<div style="overflow-x:auto"><table class="bf-table">{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def coverage_text(numerator: int, denominator: int) -> str:
    return "not measurable" if denominator == 0 else f"{numerator}/{denominator} ({numerator / denominator:.0%})"


_ICONS = {
    "Project Setup": '<path d="M5 12h14M12 5v14"/>',
    "Defense Studio": '<path d="M4 6h16v10H8l-4 4z"/>',
    "Peer Missions": '<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><path d="M3 19c1-3 3-4 5-4s4 1 5 4M11 19c1-3 3-4 5-4s4 1 5 4"/>',
    "Decision Library": '<path d="M6 4h9l3 3v13H6z"/><path d="M9 11h6M9 15h6"/>',
    "Knowledge Atlas": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/><path d="M12 4v4M20 12h-4"/>',
}


def icon(page: str) -> str:
    path = _ICONS.get(page, _ICONS["Knowledge Atlas"])
    return (f'<div class="bf-move-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{path}</svg></div>')


def statusbar(items: list[str]) -> str:
    return '<footer class="bf-statusbar">' + "".join(f"<span><i></i>{esc(i)}</span>" for i in items) + "</footer>"
