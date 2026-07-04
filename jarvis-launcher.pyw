"""
Jarvis Native Launcher
- Startet FastAPI-Server im Hintergrund
- Öffnet natives pywebview-Fenster (rahmenlos)
- System-Tray-Icon mit Menü
- Globaler Hotkey Win+J zum Ein-/Ausblenden
- Windows 11 Mica-Effekt (falls verfügbar)
"""
import os
import sys
import threading
import time
import subprocess
import ctypes
import traceback

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
SERVER_PORT = 8340
SERVER_URL = f"http://localhost:{SERVER_PORT}"

# Error-Log für silent execution (pythonw.exe)
_LOG_PATH = os.path.join(WORKSPACE, "jarvis-launcher.log")


def _rotate_log(path, max_bytes=1_000_000, backups=3):
    """Rotiert das Log beim Start, bevor der Append-Handle geöffnet wird
    (Subprocess-stdout landet im selben rohen File-Handle — RotatingFileHandler
    passt daher nicht). Läuft vor dem '--- Start'-Marker, damit read_log_tail
    den aktuellen Lauf immer in der aktiven Datei findet."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) <= max_bytes:
            return
        oldest = f"{path}.{backups}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for i in range(backups - 1, 0, -1):
            src = f"{path}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{path}.{i + 1}")
        os.replace(path, f"{path}.1")
    except OSError:
        pass  # Rotation darf den Start nie verhindern


_rotate_log(_LOG_PATH)
_log_file = open(_LOG_PATH, "a", encoding="utf-8", buffering=1)
sys.stdout = _log_file
sys.stderr = _log_file

def _write_log(msg):
    _log_file.write(msg + "\n")
    _log_file.flush()

# Nur eine Instanz erlauben
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JarvisLauncherV2Mutex")
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)


# ── Server ──────────────────────────────────────────────────────────────────

def start_server():
    return subprocess.Popen(
        [sys.executable, os.path.join(WORKSPACE, "server.py")],
        cwd=WORKSPACE,
        stdout=_log_file,
        stderr=_log_file,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def kill_zombie_on_port(port):
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = int(line.strip().split()[-1])
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                print(f"[jarvis] Zombie auf Port {port} (PID {pid}) beendet", flush=True)
                time.sleep(0.5)
                break
    except Exception as e:
        print(f"[jarvis] Port-Cleanup fehlgeschlagen: {e}", flush=True)


def server_already_running():
    import urllib.request
    try:
        urllib.request.urlopen(SERVER_URL + "/health", timeout=1)
        return True
    except:
        return False


def wait_for_server(proc=None, timeout=30):
    """Wartet auf den Server. Gibt True, "exited" (Prozess frueh gestorben,
    z.B. Config-Fehler) oder "timeout" zurueck."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return "exited"
        try:
            urllib.request.urlopen(SERVER_URL + "/health", timeout=1)
            return True
        except:
            time.sleep(0.4)
    return "timeout"


def read_log_tail(max_lines=15):
    """Liest die letzten Zeilen des aktuellen Laufs aus dem Launcher-Log
    (nur nach dem letzten '--- Start'-Marker, sonst leaken alte Runs)."""
    try:
        with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith("--- Start"):
                lines = lines[i + 1:]
                break
        return "".join(lines[-max_lines:]).strip()
    except Exception:
        return ""


def show_error_box(message):
    ctypes.windll.user32.MessageBoxW(0, message, "J.A.R.V.I.S. — Startfehler", 0x10)


# ── Multi-Monitor ────────────────────────────────────────────────────────────

def get_rightmost_monitor():
    """Gibt (x, y, w, h) des rechtesten Monitors zurück."""
    try:
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_int), ("top", ctypes.c_int),
                        ("right", ctypes.c_int), ("bottom", ctypes.c_int)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", ctypes.c_uint32)]

        rects = []

        def callback(hMon, hdcMon, lprc, dwData):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            ctypes.windll.user32.GetMonitorInfoW(hMon, ctypes.byref(info))
            r = info.rcWork
            rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(RECT), ctypes.c_size_t
        )
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MonitorEnumProc(callback), 0
        )

        if rects:
            return max(rects, key=lambda r: r[0])
    except Exception as e:
        print(f"[jarvis] Monitor-Erkennung fehlgeschlagen: {e}", flush=True)
    return (0, 0, 1920, 1080)


# ── Win11 Mica ───────────────────────────────────────────────────────────────

def apply_mica(hwnd):
    try:
        import win32mica
        win32mica.ApplyMica(hwnd, True)
        print("[jarvis] Mica-Effekt aktiviert", flush=True)
    except Exception as e:
        print(f"[jarvis] Mica nicht verfügbar: {e}", flush=True)


# ── Tray Icon ────────────────────────────────────────────────────────────────

def make_tray_image():
    from PIL import Image, ImageDraw
    sz = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, sz - 4, sz - 4], fill="#c8922a", outline="#e8b84b", width=2)
    # J in der Mitte
    d.text((sz // 2 - 5, sz // 2 - 9), "J", fill="#0d0b09")
    return img


def run_tray(window_ref):
    import pystray

    visible = [True]

    def on_show(icon, item):
        window_ref[0].show()
        visible[0] = True

    def on_hide(icon, item):
        window_ref[0].hide()
        visible[0] = False

    def on_quit(icon, item):
        icon.stop()
        window_ref[0].destroy()

    icon = pystray.Icon(
        "jarvis",
        make_tray_image(),
        "J.A.R.V.I.S.",
        menu=pystray.Menu(
            pystray.MenuItem("Anzeigen", on_show, default=True),
            pystray.MenuItem("Ausblenden", on_hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", on_quit),
        )
    )
    icon.run()


# ── Global Hotkey ────────────────────────────────────────────────────────────

def setup_hotkey(window_ref):
    try:
        import keyboard
        visible = [True]

        def toggle():
            if visible[0]:
                window_ref[0].hide()
                visible[0] = False
            else:
                window_ref[0].show()
                visible[0] = True

        # Win+J versuchen, sonst Ctrl+Alt+J
        try:
            keyboard.add_hotkey("win+j", toggle)
            print("[jarvis] Hotkey Win+J registriert", flush=True)
        except Exception:
            keyboard.add_hotkey("ctrl+alt+j", toggle)
            print("[jarvis] Hotkey Ctrl+Alt+J registriert", flush=True)
    except Exception as e:
        print(f"[jarvis] Hotkey fehlgeschlagen: {e}", flush=True)


# ── Python API für JS ────────────────────────────────────────────────────────

# Panel-Breite muss >= min_size-Breite (400) des Fensters bleiben.
PANEL_SIZE = (420, 560)
FOCUS_SIZE = (1000, 800)
WINDOW_MARGIN = 16


def set_always_on_top(window, on_top):
    """Always-on-top setzen. Der pywebview-Setter ist je nach Version wirkungslos,
    daher zusätzlich immer der Win32-Fallback über SetWindowPos (idempotent)."""
    try:
        window.on_top = on_top
    except Exception as e:
        print(f"[jarvis] on_top-Setter fehlgeschlagen: {e}", flush=True)
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, "J.A.R.V.I.S.")
        if hwnd:
            HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
            SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST if on_top else HWND_NOTOPMOST,
                0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
            )
    except Exception as e:
        print(f"[jarvis] SetWindowPos fehlgeschlagen: {e}", flush=True)


class JarvisAPI:
    """Wird über window.pywebview.api im Browser aufgerufen."""

    def __init__(self, window_ref):
        self._win = window_ref

    def minimize(self):
        try:
            self._win[0].minimize()
        except Exception:
            pass

    def hide(self):
        try:
            self._win[0].hide()
        except Exception:
            pass

    def set_window_mode(self, mode):
        """'panel': kompakt, unten rechts, always-on-top. Sonst Fokus: groß, zentriert."""
        try:
            win = self._win[0]
            mx, my, mw, mh = get_rightmost_monitor()
            if mode == "panel":
                w, h = min(PANEL_SIZE[0], mw), min(PANEL_SIZE[1], mh)
                # Erst schrumpfen, dann positionieren — vermeidet Off-Screen-Frames.
                win.resize(w, h)
                win.move(mx + mw - w - WINDOW_MARGIN, my + mh - h - WINDOW_MARGIN)
                set_always_on_top(win, True)
            else:
                w, h = min(FOCUS_SIZE[0], mw), min(FOCUS_SIZE[1], mh)
                # Erst positionieren, dann wachsen — bleibt innerhalb des Monitors.
                win.move(mx + (mw - w) // 2, my + (mh - h) // 2)
                win.resize(w, h)
                set_always_on_top(win, False)
            # Mica haengt am hwnd — nach Resize erneut anwenden (idempotent).
            hwnd = ctypes.windll.user32.FindWindowW(None, "J.A.R.V.I.S.")
            if hwnd:
                apply_mica(hwnd)
            return {"ok": True, "mode": mode}
        except Exception as e:
            print(f"[jarvis] set_window_mode fehlgeschlagen: {e}", flush=True)
            return {"ok": False, "error": str(e)}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    server_proc = None

    if server_already_running():
        print("[jarvis] Server läuft bereits.", flush=True)
    else:
        kill_zombie_on_port(SERVER_PORT)
        print("[jarvis] Starte Server...", flush=True)
        server_proc = start_server()
        result = wait_for_server(server_proc)
        if result is not True:
            if result == "exited":
                print("[jarvis] Server sofort beendet (Konfigurationsfehler?). Abbruch.", flush=True)
                tail = read_log_tail()
                msg = "Der Jarvis-Server konnte nicht starten (Konfigurationsfehler?)."
                if tail:
                    msg += f"\n\nLetzte Log-Zeilen:\n{tail}"
                msg += f"\n\nVollstaendiges Log: {_LOG_PATH}"
                show_error_box(msg)
            else:
                print("[jarvis] Server-Timeout! Abbruch.", flush=True)
                show_error_box(
                    "Der Jarvis-Server hat nicht rechtzeitig geantwortet (Timeout).\n\n"
                    f"Details im Log: {_LOG_PATH}"
                )
            if server_proc:
                server_proc.kill()
            return
        print("[jarvis] Server bereit.", flush=True)

    import webview
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = '--use-fake-ui-for-media-stream'

    # Fensterposition: rechtester Monitor
    mx, my, mw, mh = get_rightmost_monitor()
    ww = min(1000, mw)
    wh = min(800, mh)
    wx = mx + (mw - ww) // 2
    wy = my + (mh - wh) // 2

    window_ref = [None]
    api = JarvisAPI(window_ref)

    window = webview.create_window(
        "J.A.R.V.I.S.",
        SERVER_URL,
        js_api=api,
        width=ww,
        height=wh,
        x=wx,
        y=wy,
        frameless=True,
        easy_drag=False,
        background_color="#0d0b09",
        zoomable=False,
        min_size=(400, 300),
    )
    window_ref[0] = window
    api._win = window_ref

    def on_shown():
        # Mica anwenden
        hwnd = ctypes.windll.user32.FindWindowW(None, "J.A.R.V.I.S.")
        if hwnd:
            apply_mica(hwnd)
        # Hotkey registrieren
        setup_hotkey(window_ref)

    def on_closing():
        # X-Button versteckt nur, beendet nicht
        window_ref[0].hide()
        return False

    window.events.shown += on_shown
    window.events.closing += on_closing

    # Tray-Icon im Hintergrund
    threading.Thread(target=run_tray, args=(window_ref,), daemon=True).start()

    print("[jarvis] Fenster wird geöffnet...", flush=True)
    webview.start(debug=False)

    print("[jarvis] Wird beendet...", flush=True)
    if server_proc:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


if __name__ == "__main__":
    _write_log(f"\n--- Start {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    try:
        main()
    except Exception as e:
        _write_log(f"[FATAL] {e}")
        _write_log(traceback.format_exc())
