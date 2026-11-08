"""The Knowledge Constellation: an interactive SVG map of the project's decisions (Streamlit components v2).

Python sends privacy-safe nodes (counts only, see model.atlas_nodes); the browser sends back one
event, `select`, with a decision id. Nodes are focusable buttons (Tab, Enter/Space, arrow keys).
Below 560 px wide the constellation becomes a vertical list so it stays readable on phones.
The map is an instrument surface: it always uses the dark palette, in both app themes.
Only trusted, escaped data built by the app reaches the component; text is set with textContent.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from busfactor.ui.model import KNOWLEDGE, MISSION, VIEW_H, VIEW_W
from busfactor.ui.theme import INK, TOKENS

_HTML = '<div class="atlas"></div>'

_CSS = """
.atlas { font-family: "IBM Plex Sans", "Segoe UI Variable Text", system-ui, sans-serif; color: var(--text); }
.atlas svg { width: 100%; height: auto; display: block; overflow: visible; }
.node { cursor: pointer; outline: none; animation: rise .55s cubic-bezier(.2,.7,.2,1) both; animation-delay: var(--d, 0ms); }
.node .body { transition: opacity .25s ease; }
.node .body.dim { opacity: .18; }
.node .main { transition: stroke-width .15s ease, filter .25s ease; }
.node:hover .main, .node:focus-visible .main { stroke-width: 3.5; }
.node.sel .main { filter: drop-shadow(0 0 10px var(--sky)); }
.node .focus { opacity: 0; }
.node:focus-visible .focus { opacity: 1; }
.node .halo { opacity: 0; transition: opacity .25s ease; }
.node.sel .halo { opacity: 1; }
.edge { fill: none; stroke: var(--line-hi); stroke-width: 1.5; transition: opacity .25s ease; }
.edge.dim { opacity: .1; }
.spoke { stroke: var(--line); stroke-width: 1; stroke-dasharray: 1 7; }
.orbit { animation: spin 30s linear infinite; transform-box: fill-box; transform-origin: center; }
.label { font: 500 15px "IBM Plex Mono", Consolas, monospace; fill: var(--text); letter-spacing: .04em; }
.title { font: 400 14px "IBM Plex Sans", "Segoe UI", sans-serif; fill: var(--muted); }
.glyph { font: 600 20px "IBM Plex Mono", Consolas, monospace; }
.core-big { font: 300 46px "IBM Plex Sans", "Segoe UI", sans-serif; fill: var(--text); letter-spacing: -1px; }
.core-small { font: 500 11.5px "IBM Plex Mono", Consolas, monospace; fill: var(--teal); letter-spacing: .16em; }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .node, .orbit { animation: none; } .node .body, .edge, .node .halo { transition: none; } }
"""

_JS = r"""
const PENDING = "__busfactorAtlasPendingFocus";
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".atlas");
  const p = data.palette;
  for (const [k, v] of Object.entries(p)) root.style.setProperty("--" + k.replace("_", "-"), v);
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const tone = { covered: p.teal, single_point_of_failure: p.amber, no_explainer: p.red,
                 not_assessed: p.neutral, unconfirmed: p.neutral };
  const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const arc = (cx, cy, r, a0, a1) => {  // degrees, 0 = top, clockwise
    const pt = (a) => [cx + r * Math.sin(a * Math.PI / 180), cy - r * Math.cos(a * Math.PI / 180)];
    const [x0, y0] = pt(a0), [x1, y1] = pt(a1);
    return `M${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 ${(a1 - a0) > 180 ? 1 : 0} 1 ${x1.toFixed(1)},${y1.toFixed(1)}`;
  };

  function render() {
    root.textContent = "";
    const narrow = root.clientWidth > 0 && root.clientWidth < 560;
    const nodes = data.nodes.map((n, i) => narrow ? { ...n, x: 64, y: 70 + i * 108 } : n);
    const W = narrow ? 380 : data.width, H = narrow ? Math.max(140, 40 + nodes.length * 108) : data.height;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": data.summary });
    const defs = el("defs");
    const grad = el("radialGradient", { id: "core-glow" });
    grad.appendChild(el("stop", { offset: "0", "stop-color": p.teal, "stop-opacity": ".18" }));
    grad.appendChild(el("stop", { offset: "1", "stop-color": p.teal, "stop-opacity": "0" }));
    defs.appendChild(grad);
    svg.appendChild(defs);
    const pos = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const dim = new Set(data.dimmed);

    if (!narrow) {
      const cx = W / 2, cy = H / 2;
      // instrument core: glow, concentric rings, ticks, spokes
      svg.appendChild(el("circle", { cx, cy, r: 150, fill: "url(#core-glow)" }));
      [118, 92].forEach((r, i) => svg.appendChild(el("circle", { cx, cy, r, fill: "none", stroke: p.line,
        "stroke-width": 1, "stroke-dasharray": i === 0 ? "2 6" : "none" })));
      for (let k = 0; k < 60; k++) {
        const a = k * 6 * Math.PI / 180, r0 = k % 5 === 0 ? 72 : 76;
        svg.appendChild(el("line", { x1: cx + r0 * Math.sin(a), y1: cy - r0 * Math.cos(a), x2: cx + 80 * Math.sin(a),
                                     y2: cy - 80 * Math.cos(a), stroke: p.line_hi, "stroke-width": k % 5 === 0 ? 1.4 : 0.8 }));
      }
      nodes.forEach((n) => svg.appendChild(el("line", { class: "spoke", x1: cx, y1: cy, x2: n.x, y2: n.y })));
      data.edges.forEach((e) => {  // decisions sharing a concept: a curve bowed toward the core
        const a = pos[e.a], b = pos[e.b], mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        const qx = mx + (cx - mx) * 0.35, qy = my + (cy - my) * 0.35;
        const path = el("path", { class: "edge" + (dim.has(e.a) || dim.has(e.b) ? " dim" : ""),
                                  d: `M${a.x},${a.y} Q${qx.toFixed(1)},${qy.toFixed(1)} ${b.x},${b.y}` });
        path.appendChild(el("title", {}, "Shared concept: " + e.concepts.join(", ")));
        svg.appendChild(path);
      });
      svg.appendChild(el("circle", { cx, cy, r: 64, fill: p.ink_2, stroke: p.line_hi, "stroke-width": 1.2 }));
      svg.appendChild(el("text", { class: "core-big", x: cx, y: cy + 10, "text-anchor": "middle" }, data.core.big));
      svg.appendChild(el("text", { class: "core-small", x: cx, y: cy + 32, "text-anchor": "middle" }, data.core.small));
    }

    nodes.forEach((n, i) => {
      const selected = n.id === data.selected;
      const g = el("g", { class: "node" + (selected ? " sel" : ""), tabindex: 0, role: "button",
                          "data-id": n.id, "aria-pressed": selected ? "true" : "false", "aria-label": n.aria });
      g.style.setProperty("--d", `${i * 70}ms`);
      const body = el("g", { class: "body" + (dim.has(n.id) ? " dim" : "") });
      const r = n.critical ? 30 : 25, c = tone[n.state];
      body.appendChild(el("circle", { class: "halo", cx: n.x, cy: n.y, r: r + 26, fill: "none", stroke: p.sky,
                                      "stroke-width": 1.5, "stroke-dasharray": "3 5" }));
      body.appendChild(el("circle", { class: "focus", cx: n.x, cy: n.y, r: r + 32, fill: "none",
                                      stroke: p.focus, "stroke-width": 3 }));
      if (n.mission === "proposed" || n.mission === "accepted") {
        body.appendChild(el("circle", { class: "orbit", cx: n.x, cy: n.y, r: r + 19, fill: "none", stroke: p.violet,
                                        "stroke-width": 2, "stroke-dasharray": n.mission === "accepted" ? "12 6" : "3 7" }));
      }
      if (n.mission === "verified") {
        body.appendChild(el("circle", { cx: n.x, cy: n.y, r: r + 15, fill: "none", stroke: p.teal, "stroke-width": 1.5 }));
        body.appendChild(el("circle", { cx: n.x, cy: n.y, r: r + 20, fill: "none", stroke: p.teal, "stroke-width": 1 }));
      }
      // explainer arcs: one segment per member, filled = can explain it (a count, no names)
      const seats = Math.max(1, Math.min(n.team, 10)), span = 360 / seats;
      for (let k = 0; k < seats; k++) {
        body.appendChild(el("path", { d: arc(n.x, n.y, r + 8, k * span + 6, (k + 1) * span - 6), fill: "none",
                                      stroke: k < n.explainers ? c : p.line_hi, "stroke-width": 3.2,
                                      "stroke-linecap": "round" }));
      }
      body.appendChild(el("circle", { class: "main", cx: n.x, cy: n.y, r, fill: n.state === "unconfirmed" ? p.ink : c,
                                      "fill-opacity": n.state === "unconfirmed" ? 1 : 0.16, stroke: c, "stroke-width": 2,
                                      "stroke-dasharray": n.state === "unconfirmed" ? "5 5" : "none" }));
      body.appendChild(el("text", { class: "glyph", x: n.x, y: n.y + 7, "text-anchor": "middle", fill: c }, n.glyph));
      const lx = narrow ? n.x + r + 26 : n.x, anchor = narrow ? "start" : "middle";
      body.appendChild(el("text", { class: "label", x: lx, y: narrow ? n.y - 6 : n.y + r + 30, "text-anchor": anchor }, n.label));
      body.appendChild(el("text", { class: "title", x: lx, y: narrow ? n.y + 14 : n.y + r + 49, "text-anchor": anchor },
                          short(n.title, narrow ? 32 : 28)));
      if (narrow) body.appendChild(el("text", { class: "title", x: lx, y: n.y + 33, "text-anchor": anchor }, n.stateLabel));
      g.appendChild(el("title", {}, n.aria));
      g.appendChild(body);
      const choose = () => { window[PENDING] = n.id; setTriggerValue("select", n.id); };
      g.addEventListener("click", choose);
      g.addEventListener("keydown", (ev) => {
        const all = [...svg.querySelectorAll(".node")];
        const at = all.indexOf(g);
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); choose(); }
        if (ev.key === "ArrowRight" || ev.key === "ArrowDown") { ev.preventDefault(); all[(at + 1) % all.length].focus(); }
        if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") { ev.preventDefault(); all[(at - 1 + all.length) % all.length].focus(); }
      });
      svg.appendChild(g);
    });
    root.appendChild(svg);
    // After a selection, Streamlit reruns and this map is drawn again: put keyboard focus back on the
    // chosen star once it shows as selected. Kept on window because the module can be re-evaluated.
    const pending = window[PENDING];
    if (pending && pending === data.selected) {
      window[PENDING] = null;
      const again = svg.querySelector(`.node[data-id="${CSS.escape(pending)}"]`);
      if (again) again.focus({ preventScroll: true });
    }
  }

  render();
  let wasNarrow = root.clientWidth < 560;
  const ro = new ResizeObserver(() => {
    const narrow = root.clientWidth < 560;
    if (narrow !== wasNarrow) { wasNarrow = narrow; render(); }
  });
  ro.observe(root);
  return () => ro.disconnect();
}
"""

_atlas = st.components.v2.component("busfactor.knowledge_constellation", html=_HTML, css=_CSS, js=_JS)


def map_palette() -> dict[str, str]:
    """The map is an instrument surface: always the dark palette, whatever the app theme."""
    d = TOKENS["dark"]
    return {"teal": d["teal"], "amber": d["amber"], "red": d["red"], "neutral": d["neutral"], "violet": d["violet"],
            "sky": d["sky"], "focus": d["focus"], "text": INK["ink_text"], "muted": INK["ink_muted"],
            "line": INK["ink_line"], "line_hi": d["line_strong"], "ink": INK["ink"], "ink_2": INK["ink_2"]}


def node_aria(node: dict) -> str:
    state = KNOWLEDGE[node["state"]][0]
    who = (f"{node['explainers']} of {node['team']} members can explain it" if node["state"] != "unconfirmed"
           else "not counted until confirmed")
    mission = f", {MISSION[node['mission']][0].lower()}" if node["mission"] != "none" else ""
    return f"{node['label']}, {node['title']}: {state.lower()}, {who}{mission}. Press Enter to open."


def knowledge_constellation(nodes: list[dict], edges: list[dict], *, selected: Optional[str], dimmed: list[str],
                            palette: Optional[dict[str, str]] = None, core: tuple[str, str] = ("—", ""),
                            key: str = "atlas") -> Optional[str]:
    """Render the map; returns the decision id the user just selected (or None). `palette` is ignored:
    the instrument always uses the dark palette (kept as a parameter for callers)."""
    payload_nodes = [{**n, "aria": node_aria(n), "glyph": KNOWLEDGE[n["state"]][2],
                      "stateLabel": KNOWLEDGE[n["state"]][0]} for n in nodes]
    summary = (f"Knowledge constellation of {len(nodes)} decisions. "
               + "; ".join(f"{n['label']} {KNOWLEDGE[n['state']][0]}" for n in nodes))
    result = _atlas(key=key, data={"nodes": payload_nodes, "edges": edges, "selected": selected, "dimmed": dimmed,
                                   "palette": map_palette(), "core": {"big": core[0], "small": core[1]},
                                   "width": VIEW_W, "height": VIEW_H, "summary": summary},
                    on_select_change=lambda: None)
    return getattr(result, "select", None) if result is not None else None
