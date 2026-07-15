# Phase 7 — Evidenz (Messungen, E2E, A11y-Tree)

Alle Messungen gegen das gestubbte Harness `127.0.0.1:8341` (Dummy-Keys), headless Chromium/Playwright. **Keine Secrets/persönlichen Daten**, keine kostenpflichtigen APIs. Datum 2026-07-13.

## Sicherheit / Datenschutz (Priorität 1)

- **GET /settings (Laufzeit, HTTP 200):** Felder = `apps, city, elevenlabs_voice_id, launcher, music_folder, music_volume, obsidian_inbox_folder, obsidian_inbox_path, selected_music_file, user_address, user_name, user_role`. **`body_contains_api_key: false`**, `suspected_leaks: []`. Keys strukturell ausgeschlossen (`server.py::_public_settings` nutzt nur `UI_EDITABLE_KEYS`; `PROTECTED_KEYS` = beide API-Keys).
- API-Keys erscheinen nicht im DOM, nicht im Settings-Form (expliziter Hinweistext), nicht in Fehlermeldungen (nur Schlüsselnamen).

## Kontrast (WCAG AA, gemessen)

status 7.7 · journal-title 7.12 · kbd-hint 4.89 · ask-hint 4.89 · sc-conn 4.89 · cc-empty 4.89 · msg-time 4.52 · search-count 4.52 — **alle informationstragenden Texte ≥ 4.5:1 (AA)**. Farbe nie einziges Zustandsmerkmal (Wort + Farbe + Dot + Licht).

## Tastaturfokus (gemessen)

- Globaler `:focus-visible` 2px-Messing-Ring auf allen fokussierbaren Buttons (Tab-Sequenz Jarvis-Seite: skip-link, pn-btn ×2, wm-btn ×3, btn-min, btn-close, btn-copy-all, msg-copy, stop-btn, mute-btn = Ring sichtbar).
- Nach Fix zusätzlich Ring auf cc-tab, profile-tab, profile-action, map-zone, map-zone-full (Kontrollzentrum).
- Inputs (text-input, transcript-search) zeigen Fokus per Rahmen + Halo (konventionell).
- **Weg B (Monitor-Zuweisung, SR-Primärroute):** `.app-position`-Selects via `:focus-within` beim Tab-in enthüllt, sichtbar, per `<label for>` benannt — keyboard-erreichbar.

## Responsive / Zoom (gemessen)

- **H-Overflow = 0** bei 1920/1600/1366/1024/900/768/600/430 (+ Phase-6-Sweep 1920→420).
- **Orb-Clip Mitte 1000×800:** `orb_top` 10 → **45** (klar über Titelleiste 38). Vollbild 1920×1080 unverändert (orb 196, top 86). 200 %-Zoom-Rest (<~600px Höhe) dokumentiert (P3, dekorativ/aria-hidden).
- `color-scheme: dark` aktiv auf `html` + nativen `<select>` (colorScheme=dark).

## A11y-Tree (Struktur, gemessen — **Tree-Prüfung, kein echter Screenreader-Test**)

- **Landmarken:** `nav[Bereich]`, `main[Gespräch]`, `footer[Gerätestatus und Steuerung]`, `banner` (win-bar).
- **Genau eine `<h1>` je Seite exponiert** (nach Review-Fix F1): Jarvis-Seite „Gespräch mit Jarvis", Kontrollzentrum „Kontrollzentrum" — die jeweils inaktive Bereichs-h1 ist `display:none` (vorher waren beide sr-only-h1 gleichzeitig im Tree).
- **Heading-Walk Kontrollzentrum:** H1 Kontrollzentrum → **H2 Heute** → H3 Offene Aufgaben → H3 Inbox heute → H3 Zuletzt bearbeitet → H2 Apps → H2 Aktionen → H2 System — **monoton, kein Sprung** (h1→h3 behoben; keine zweite konkurrierende h1 mehr).
- **Live-Regionen:** boot-fallback (status), status-row (status), search-count (status), cc-map-status/cc-app-msg/music-msg/settings-msg (polite), Fehler-Banner je Element `role=alert` (Störung) / `role=status` (Warnung). Keine konkurrierenden/doppelten Live-Regionen.
- **Icon-Buttons:** btn-min „Minimieren", btn-close „Fenster ausblenden", .eb-close „Meldung schließen" (aria-label).

## End-to-End (30 Abläufe, gestubbtes Harness)

| # | Ablauf | Ergebnis |
|---|---|---|
| 1 | Anwendung öffnen | bestanden |
| 2 | Verbindungszustand verstehen | bestanden („Server verbunden") |
| 3 | Spracheingabe starten (PTT) | teilweise — PTT-Zustand ok; **echtes STT nicht prüfbar** (Browser-SpeechRecognition + Mikro, nichtdeterministisch) |
| 4 | Listening erkennen | bestanden |
| 5 | Thinking erkennen | bestanden |
| 6 | Antwort anzeigen | bestanden (WS-Runde übers Harness) |
| 7 | Speaking erkennen | bestanden |
| 8 | Sprachausgabe stoppen | bestanden (Stop-Button) |
| 9 | laufende Aktion stoppen | bestanden (Esc kaskadiert) |
| 10 | Mikrofon stummschalten | bestanden (aria-pressed=true) |
| 11 | Mikrofon aktivieren | bestanden |
| 12 | Textanfrage senden | bestanden (Nachrichten 1→3) |
| 13 | nach Fehler weiterarbeiten | bestanden (Eingabe bleibt bedienbar) |
| 14 | Transcript durchsuchen | bestanden („2 von 3 Einträgen") |
| 15 | Nachricht kopieren | bestanden |
| 16 | vollständiges Transcript kopieren | bestanden |
| 17 | Kontrollzentrum öffnen | bestanden |
| 18 | App starten | bestanden (Öffnen-POST an **gestubbten** Launcher; echter Prozessstart nicht prüfbar) |
| 19 | Autostart ändern | bestanden (Toggle) |
| 20 | App einem Monitorbereich zuweisen | bestanden (Zone fullscreen→left_half, „Obsidian: Platzierung gespeichert."; Weg B keyboard-erreichbar) |
| 21 | Profil wechseln | bestanden (2 Profile) |
| 22 | Profil verwalten | bestanden (Neu/Aktion) |
| 23 | Einstellungen bearbeiten | bestanden (dirty-Pill) |
| 24 | Änderung speichern | bestanden („Gespeichert ✓") |
| 25 | Änderung abbrechen | bestanden (Verwerfen-Rückfrage) |
| 26 | Musik auswählen | bestanden (3 Titel im Stub) |
| 27 | Musik entfernen | bestanden |
| 28 | Fenstermodus wechseln | bestanden (Panel/Fokus/Vollbild aria-pressed) |
| 29 | vollständige Tastaturnavigation | bestanden (12 distinkte Fokusziele, logische Reihenfolge) |
| 30 | Reduced-Motion-Betrieb | bestanden (reduced-Context: 0 Animationen, statischer Glow, Funktionen identisch) |

**Konsolenfehler über alle E2E-Läufe: 0.**

## Nicht prüfbar (mit manueller Prüfanweisung)

- **Echtes STT / Spracherkennung (Ablauf 3):** Browser-`SpeechRecognition` braucht echtes Mikrofon + Sprache, nichtdeterministisch und im Harness gestubbt. *Manuell:* Jarvis per Launcher starten, „Jarvis" sagen, Zuhören-Zustand + erkannten Text prüfen.
- **Echte Sprachausgabe (ElevenLabs, Abläufe 6/7):** kostenpflichtige API, im Harness durch TTS-Stub ersetzt. *Manuell:* echte Antwort abwarten, Audio + Speaking-Puls + Stop prüfen.
- **Echter Claude-Call (Abläufe 6/12):** kostenpflichtig, im Harness durch FakeAI ersetzt. *Manuell:* echte Frage stellen, inhaltliche Antwort prüfen.
- **Echter App-Start (Ablauf 18):** startet reale Windows-Prozesse; im Harness gestubbt. *Manuell:* „Öffnen" klicken, Fensterplatzierung auf dem Zielmonitor prüfen.
- **Doppelklatschen-Trigger, native Fenstermodus-Größe (pywebview):** außerhalb der Browser-Prüfung. *Manuell:* im Launcher testen.
