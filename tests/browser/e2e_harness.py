"""Gemeinsame E2E-Infrastruktur fuer die Jarvis-Browsertests.

Bietet:
  - ``JarvisServer``: startet ``e2e_server.py`` als Subprozess auf einem freien
    Loopback-Port, wartet auf Readiness (GET /health), raeumt sauber auf; ein
    eigenes Logfile pro Lauf (nur bei Fehlern als Artefakt aufbewahrt).
  - ``browser_context``: Chromium-Kontext mit deterministischen Init-Skripten
    (Mikrofonmodus PTT, optional feste Uhr + Animationen aus), Fake-Media-Flags,
    strikter Netzwerk-Policy (nur lokale Origin + data:/blob:), sowie Sammlern
    fuer Console-Errors, Page-Errors, fehlgeschlagene lokale Requests und
    unerwartete externe Hosts.
  - ``Collectors.assert_clean``: erzwingt die Fehlerpolitik aus
    docs/quality/BROWSER_TEST_STRATEGY.md.

Bewusst KEINE festen Sleeps zur Synchronisation in den Tests — hier nur die
Prozess-Readiness pollt (das ist kein UI-Warten).
"""
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
E2E_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_server.py")
# In CI ueber JARVIS_E2E_ARTIFACTS auf einen Workspace-Pfad zeigen lassen
# (dann werden Server-Logs bei Fehlern als Failure-Artefakt hochgeladen).
ARTIFACT_DIR = os.environ.get("JARVIS_E2E_ARTIFACTS") or os.path.join(
    tempfile.gettempdir(), "jarvis-e2e-artifacts")

# ── Deterministische Init-Skripte (uebernommen aus capture_baseline.py) ──────
INIT_MIC_PTT = "localStorage.setItem('jarvis.micMode', 'ptt');"

INIT_FREEZE_CLOCK = """
(() => {
    const fixed = 1783154400000; // 2026-07-11T10:00:00Z, stabil
    const RealDate = Date;
    class FrozenDate extends RealDate {
        constructor(...args) { args.length ? super(...args) : super(fixed); }
        static now() { return fixed; }
    }
    FrozenDate.parse = RealDate.parse;
    FrozenDate.UTC = RealDate.UTC;
    window.Date = FrozenDate;
})();
"""

INIT_FREEZE_STYLE = """
document.addEventListener('DOMContentLoaded', () => {
    const s = document.createElement('style');
    s.textContent = '*, *::before, *::after { animation: none !important; ' +
        'transition: none !important; caret-color: transparent !important; }';
    document.head.appendChild(s);
});
"""

# Steuerbarer WebSocket-Wrapper: erlaubt dem Test, eine Verbindung gezielt zu
# kappen (Reconnect-Flow), ohne den Server toeten zu muessen (Token bliebe sonst
# ungueltig). Der Wrapper zaehlt Verbindungen und merkt sich die letzte Instanz.
INIT_WS_CONTROL = """
(() => {
    const Real = window.WebSocket;
    window.__wsInstances = [];
    window.__wsConnectCount = 0;
    function Wrapped(url, protocols) {
        const ws = protocols ? new Real(url, protocols) : new Real(url);
        window.__wsConnectCount++;
        window.__wsInstances.push(ws);
        window.__lastWs = ws;
        return ws;
    }
    Wrapped.prototype = Real.prototype;
    Wrapped.CONNECTING = Real.CONNECTING; Wrapped.OPEN = Real.OPEN;
    Wrapped.CLOSING = Real.CLOSING; Wrapped.CLOSED = Real.CLOSED;
    window.WebSocket = Wrapped;
})();
"""

# WebSocket, der nie verbindet und nach 150 ms onclose feuert (Disconnected-Shot).
INIT_WS_BLOCK = """
window.WebSocket = class {
    constructor() { this.readyState = 3; setTimeout(() => this.onclose && this.onclose({}), 150); }
    send() {} close() {}
};
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class JarvisServer:
    """Startet e2e_server.py als Subprozess und raeumt ihn wieder ab."""

    def __init__(self, name="e2e"):
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.tmp = os.path.join(tempfile.gettempdir(), f"jarvis-e2e-{self.port}")
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        self.log_path = os.path.join(ARTIFACT_DIR, f"server-{name}-{self.port}.log")
        self._log = None
        self.proc = None

    def __enter__(self):
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        self._log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, E2E_SERVER, "--port", str(self.port), "--tmp", self.tmp],
            stdout=self._log, stderr=subprocess.STDOUT, env=env, cwd=ROOT,
        )
        self._wait_ready()
        return self

    def _wait_ready(self, timeout=45):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"E2E-Server beendete sich frueh (Log: {self.log_path})")
            try:
                with urllib.request.urlopen(self.base_url + "/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                time.sleep(0.3)
        raise TimeoutError(f"E2E-Server nicht bereit (Log: {self.log_path})")

    def scenario(self, replies=None, llm_delay=0.0, action_delay=0.0):
        payload = json.dumps({
            "replies": replies or [], "llm_delay": llm_delay, "action_delay": action_delay,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/__e2e__/scenario", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def __exit__(self, exc_type, exc, tb):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self._log:
            self._log.close()
        # Log nur bei Fehler behalten, sonst entfernen (kein Muell).
        if exc_type is None:
            with contextlib.suppress(OSError):
                os.remove(self.log_path)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


class Collectors:
    def __init__(self):
        self.console_errors = []
        self.page_errors = []
        self.failed_requests = []
        self.external_hosts = []
        self.allowed_console_errors = []

    def allow_console_error(self, substring):
        """Einen ERWARTETEN Browser-Log-Eintrag zulassen.

        Nur fuer Flows, die bewusst eine Nicht-2xx-Antwort provozieren (z.B. den
        409-Konflikt): Chromium loggt jede fehlgeschlagene Ressource selbsttaetig
        als console.error. Die strenge Politik gilt fuer alles andere weiter —
        die Ausnahme ist eng, benannt und muss im Flow begruendet sein.
        """
        self.allowed_console_errors.append(substring)

    def assert_clean(self, context=""):
        problems = []
        unexpected = [m for m in self.console_errors
                      if not any(a in m for a in self.allowed_console_errors)]
        if unexpected:
            problems.append(f"console.error: {unexpected}")
        if self.page_errors:
            problems.append(f"pageerror: {self.page_errors}")
        if self.failed_requests:
            problems.append(f"failed local requests: {self.failed_requests}")
        if self.external_hosts:
            problems.append(f"unerwartete externe Hosts: {self.external_hosts}")
        if problems:
            raise AssertionError(f"[{context}] Fehlerpolitik verletzt:\n  " + "\n  ".join(problems))


def attach_collectors(page, base_url, collectors):
    """Console-/Page-Error-, Failed-Request- und Netzwerk-Policy-Sammler anhaengen."""
    aborted = set()

    page.on("console", lambda m: collectors.console_errors.append(m.text)
            if m.type == "error" else None)
    page.on("pageerror", lambda e: collectors.page_errors.append(str(e)))

    def on_failed(request):
        if request.url in aborted:
            return  # bewusst geblockter externer Request
        if request.url.startswith(base_url):
            collectors.failed_requests.append(f"{request.url} :: {request.failure}")

    page.on("requestfailed", on_failed)

    def route_handler(route):
        url = route.request.url
        if url.startswith(base_url) or url.startswith("data:") or url.startswith("blob:"):
            route.continue_()
        else:
            aborted.add(url)
            collectors.external_hosts.append(url)
            route.abort()

    page.context.route("**/*", route_handler)


@contextlib.contextmanager
def browser_context(playwright, base_url, *, reduced_motion=None, freeze=True,
                    viewport=(1920, 1080), ws_init=INIT_WS_CONTROL, extra_init=None):
    """Deterministischer Chromium-Kontext mit Sammlern + Netzwerk-Policy.

    ``ws_init`` waehlt den WebSocket-Wrapper (steuerbar) oder INIT_WS_BLOCK
    (nie verbunden). ``freeze`` friert Uhr + Animationen ein (fuer Visual/
    Determinismus); fuer Reconnect-Tests mit Timern kann das deaktiviert werden.
    """
    browser = playwright.chromium.launch(headless=True, args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
    ])
    context = browser.new_context(
        viewport={"width": viewport[0], "height": viewport[1]},
        permissions=["microphone"], locale="de-DE",
        reduced_motion=reduced_motion,
    )
    context.add_init_script(INIT_MIC_PTT)
    if ws_init:
        context.add_init_script(ws_init)
    if freeze:
        context.add_init_script(INIT_FREEZE_CLOCK)
        context.add_init_script(INIT_FREEZE_STYLE)
    if extra_init:
        context.add_init_script(extra_init)
    collectors = Collectors()
    page = context.new_page()
    attach_collectors(page, base_url, collectors)
    try:
        yield page, collectors
    finally:
        context.close()
        browser.close()


def open_jarvis(page, base_url, expect_connected=True):
    """Zur Jarvis-Seite navigieren und auf einen verifizierten Startzustand warten.

    Readiness ist NICHT networkidle (Jarvis haelt den WS offen), sondern der
    sichtbare 'Server verbunden'-Zustand plus die beantwortete Auto-Begruessung.
    """
    page.goto(base_url)
    page.wait_for_selector("body.jarvis-ready")
    if expect_connected:
        page.wait_for_function(
            "document.getElementById('sc-conn-text') && "
            "document.getElementById('sc-conn-text').textContent === 'Server verbunden'",
            timeout=15000,
        )
        # Auto-Begruessung ('Jarvis activate') wurde vom Stub beantwortet.
        page.wait_for_function(
            "document.querySelectorAll('#transcript .msg.jarvis').length >= 1",
            timeout=15000,
        )
