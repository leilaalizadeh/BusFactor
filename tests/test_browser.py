"""OPT-IN real-browser checks of the Knowledge Constellation (the replacement for the old 3D map).

Skipped unless RUN_BROWSER_TESTS=1 and Google Chrome is installed. It starts the real Streamlit server on a
throwaway database and drives headless Chrome through the DevTools protocol (no extra packages: the
`websockets` library ships with Streamlit). Run:  set RUN_BROWSER_TESTS=1 && python -m pytest tests/test_browser.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.getenv("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1" or not Path(CHROME).exists(),
                                reason="real-browser test: set RUN_BROWSER_TESTS=1 (needs Google Chrome)")

FIND = """(() => { const seen = [document];
  while (seen.length) { const r = seen.pop();
    const hit = r.querySelector && r.querySelector('%s'); if (hit) return hit;
    r.querySelectorAll && r.querySelectorAll('*').forEach(e => e.shadowRoot && seen.push(e.shadowRoot)); }
  return null; })()"""
ALL_NODES = """(() => { const out = []; const seen = [document];
  while (seen.length) { const r = seen.pop();
    r.querySelectorAll && r.querySelectorAll('.node').forEach(n => out.push(n));
    r.querySelectorAll && r.querySelectorAll('*').forEach(e => e.shadowRoot && seen.push(e.shadowRoot)); }
  return out; })()"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_http(url, tries=160):
    for _ in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=2).read()
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"no answer from {url}")


class Browser:
    def __init__(self, ws_url):
        from websockets.sync.client import connect
        self.ws, self.n = connect(ws_url, max_size=None), 0

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                assert "error" not in msg, msg
                return msg.get("result", {})

    def js(self, expr):
        return self.call("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")

    def until(self, expr, timeout=45):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expr):
                return True
            time.sleep(0.4)
        return False

    def open(self, query, width=1440, height=1000, mobile=False, reduced_motion=False):
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=mobile)
        self.call("Emulation.setEmulatedMedia", features=[
            {"name": "prefers-reduced-motion", "value": "reduce" if reduced_motion else "no-preference"}])
        self.call("Page.navigate", url=f"{self.base}/?{query}")
        time.sleep(1)
        assert self.until("!!document.querySelector('h1')"), "page did not render"


@pytest.fixture(scope="module")
def browser():
    tmp = tempfile.mkdtemp()
    app_port, cdp_port = free_port(), free_port()
    env = dict(os.environ, DEMO_MODE="true", BUSFACTOR_DB=os.path.join(tmp, "browser.db"),
               BUSFACTOR_UPLOADS=os.path.join(tmp, "uploads"))
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.headless",
                               "true", "--server.port", str(app_port), "--browser.gatherUsageStats", "false"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={cdp_port}",
                               f"--user-data-dir={tempfile.mkdtemp()}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_http(f"http://localhost:{app_port}/_stcore/health")
        wait_http(f"http://localhost:{cdp_port}/json/version")
        page = next(t for t in json.loads(wait_http(f"http://localhost:{cdp_port}/json")) if t["type"] == "page")
        b = Browser(page["webSocketDebuggerUrl"])
        b.base = f"http://localhost:{app_port}"
        b.call("Page.enable")
        b.call("Runtime.enable")
        yield b
    finally:
        chrome.terminate()
        server.terminate()
        server.wait(timeout=10)


def test_every_star_is_a_labelled_focusable_button(browser):
    browser.open("page=1&as=M04")
    assert browser.until(f"{ALL_NODES}.length === 5")
    nodes = browser.js(f"{ALL_NODES}.map(n => [n.getAttribute('role'), n.getAttribute('tabindex'), "
                       "n.getAttribute('aria-label')])")
    assert all(role == "button" and tab == "0" and "Press Enter to open" in label for role, tab, label in nodes)
    d03 = next(label for _, _, label in nodes if label.startswith("D03,"))
    assert "Use F1 instead of accuracy" in d03 and "single point of failure, 1 of 4 members can explain it" in d03


def test_click_and_enter_open_the_spotlight_and_keep_focus(browser):
    browser.open("page=1&as=M04")
    assert browser.until("!!" + FIND % '.node[data-id="D03"]')
    browser.js(f"({FIND % '.node[data-id=\"D03\"]'}).dispatchEvent(new MouseEvent('click', {{bubbles: true}}))")
    assert browser.until("document.body.innerText.toUpperCase().includes('DECISION SPOTLIGHT · D03')")
    time.sleep(1)
    browser.js(f"(() => {{ const n = {FIND % '.node[data-id=\"D02\"]'}; n.focus(); "
               "n.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })()")
    assert browser.until("document.body.innerText.toUpperCase().includes('DECISION SPOTLIGHT · D02')")
    # the map itself must show the chosen star as selected (not only the Python spotlight) ...
    assert browser.until(f"(() => {{ const s = {FIND % '.node.sel'}; return !!s && s.getAttribute('data-id') === 'D02'; }})()",
                         timeout=15)
    # ... and, after the rerun re-draws it, keyboard focus must be back on that star
    assert browser.until(f"(() => {{ const n = {FIND % '.node[data-id=\"D02\"]'}; "
                         "return !!n && n.getRootNode().activeElement === n; })()", timeout=15)


def test_arrow_keys_move_between_stars(browser):
    browser.open("page=1&as=M04")
    assert browser.until("!!" + FIND % '.node[data-id="D01"]')
    moved = browser.js(f"""(() => {{ const n = {FIND % '.node[data-id="D01"]'}; n.focus();
        n.dispatchEvent(new KeyboardEvent('keydown', {{key: 'ArrowRight', bubbles: true}}));
        return n.getRootNode().activeElement.getAttribute('data-id'); }})()""")
    assert moved == "D02"


def test_reduced_motion_stops_the_animation(browser):
    browser.open("page=1&as=M04", reduced_motion=True)
    assert browser.until("!!" + FIND % ".node")
    assert browser.js(f"getComputedStyle({FIND % '.node'}).animationName") == "none"


@pytest.mark.parametrize("page", [0, 1, 2, 3, 4, 5, 6])
def test_no_horizontal_overflow_on_a_phone(browser, page):
    browser.open(f"page={page}&as=M04", width=390, height=844, mobile=True)
    time.sleep(1.5)
    assert browser.js("document.documentElement.scrollWidth - window.innerWidth") <= 0
