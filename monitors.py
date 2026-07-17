"""
Jarvis V2 — Monitor-Erkennung (Windows, ctypes)

Liefert die physischen Monitore fuer die Monitor-Map im Fokus-Modus.
Die semantischen IDs spiegeln die Placement-Engine in launch-session.ps1:
ein Monitor -> "primary"; mehrere -> ganz links "left", ganz rechts "right";
mittlere Monitore (3+) bekommen keine ID (das Placement-Modell adressiert
nur primary/left/right/leftmost/rightmost).

Nur Stdlib/ctypes, keine neuen Dependencies. ``detect_monitors`` wirft NIE —
bei jedem Fehler (Nicht-Windows, ctypes-Problem) kommt eine leere Liste
zurueck und das Frontend faellt auf die virtuelle Standardansicht zurueck.

Bewusst KEIN SetProcessDPIAware: der Server kann im pywebview-Prozess laufen;
fuer die proportionale Darstellung sind skalierte Koordinaten gleichwertig.
"""

import obslog

_MONITORINFOF_PRIMARY = 1


def _enum_monitors_raw() -> list[dict]:
    """Rohe Monitor-Rechtecke via EnumDisplayMonitors/GetMonitorInfoW."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # wirft auf Nicht-Windows -> detect_monitors faengt

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    raw: list[dict] = []

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )

    def _callback(hmonitor, _hdc, _lprect, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            raw.append({
                "x": r.left, "y": r.top,
                "width": r.right - r.left, "height": r.bottom - r.top,
                "primary": bool(info.dwFlags & _MONITORINFOF_PRIMARY),
            })
        return 1  # weiter enumerieren

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_callback), 0)
    return raw


def _assign_ids(raw: list[dict]) -> list[dict]:
    """Semantische IDs/Labels vergeben — pur und testbar.

    Sortiert nach x; spiegelt die PS1-Aufloesung (left==leftmost,
    right==rightmost, Einzelmonitor==primary).
    """
    monitors = [dict(m) for m in sorted(raw, key=lambda m: m.get("x", 0))]
    if not monitors:
        return []
    if len(monitors) == 1:
        monitors[0]["id"] = "primary"
        monitors[0]["label"] = "Primärer Monitor"
        return monitors
    for i, mon in enumerate(monitors):
        if i == 0:
            mon["id"], mon["label"] = "left", "Linker Monitor"
        elif i == len(monitors) - 1:
            mon["id"], mon["label"] = "right", "Rechter Monitor"
        else:
            # Mittlere Monitore sind im Placement-Modell nicht adressierbar.
            mon["id"], mon["label"] = None, f"Monitor {i + 1}"
    return monitors


def detect_monitors() -> list[dict]:
    """Monitore erkennen; leere Liste bei jedem Fehler (Frontend-Fallback)."""
    try:
        return _assign_ids(_enum_monitors_raw())
    except Exception as e:
        obslog.event("monitor.detect_failed", error_type=type(e).__name__)
        return []
