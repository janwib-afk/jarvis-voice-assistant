#!/usr/bin/env python3
"""
Jarvis — Double Clap Trigger
Listens to mic. Detects two claps within 1.2s, min 0.1s apart.
On trigger: runs scripts/launch-session.ps1 then exits.
"""

import ctypes
import json
import os
import subprocess
import time

# Repo-Root = Elternverzeichnis von scripts/. Dient als Fallback, wenn
# config.json kein workspace_path enthaelt oder fehlt/ungueltig ist —
# config_loader.REQUIRED_KEYS verlangt workspace_path naemlich nicht.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024
THRESHOLD = 0.15       # RMS volume spike threshold — lower = more sensitive
MIN_GAP = 0.1          # Minimum seconds between claps
MAX_GAP = 1.2          # Maximum seconds between claps — more time for second clap
COOLDOWN = 3.0         # Seconds to ignore after trigger fires


def resolve_script_path(config_path: str = CONFIG_PATH, repo_root: str = REPO_ROOT) -> str:
    """Ermittelt den Pfad zu launch-session.ps1 — robust ohne Crash.

    Nutzt ``workspace_path`` aus config.json, falls vorhanden; sonst das Repo-Root
    (Elternverzeichnis von scripts/). Fehlt config.json oder ist sie kein gueltiges
    JSON, wird eine verstaendliche Meldung ausgegeben und das Repo-Root verwendet.
    """
    workspace_path = repo_root
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if isinstance(config, dict) and config.get("workspace_path"):
            workspace_path = config["workspace_path"]
    except FileNotFoundError:
        print(
            f"[jarvis] config.json nicht gefunden ({config_path}) — "
            f"nutze Repo-Root {repo_root}.",
            flush=True,
        )
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[jarvis] config.json konnte nicht gelesen werden ({e}) — "
            f"nutze Repo-Root {repo_root}.",
            flush=True,
        )
    return os.path.join(workspace_path, "scripts", "launch-session.ps1")


def main():
    # Audio-Backend erst hier importieren — so bleibt der Modul-Import (z.B. in
    # Tests fuer resolve_script_path) frei von sounddevice/numpy.
    import numpy as np
    import sounddevice as sd

    script_path = resolve_script_path()

    last_clap_time = 0.0
    triggered = False

    def audio_callback(indata, frames, time_info, status):
        nonlocal last_clap_time, triggered

        if triggered:
            return

        now = time.time()
        rms = float(np.sqrt(np.mean(indata ** 2)))

        if rms > THRESHOLD:
            gap = now - last_clap_time

            if gap >= MIN_GAP:
                if gap <= MAX_GAP and last_clap_time > 0:
                    # Second clap — fire trigger and shut down
                    print(f"[jarvis] Double clap detected! Firing launch script. Shutting down.", flush=True)
                    triggered = True
                    last_clap_time = 0.0
                    subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path])
                    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
                else:
                    # First clap
                    print(f"[jarvis] First clap detected (rms={rms:.3f})", flush=True)
                    last_clap_time = now

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        channels=1,
        dtype="float32",
        callback=audio_callback,
    ):
        print("[jarvis] Listening for double clap...", flush=True)
        while not triggered:
            time.sleep(0.1)
        print("[jarvis] Trigger fired — stopped listening.", flush=True)


if __name__ == "__main__":
    main()
