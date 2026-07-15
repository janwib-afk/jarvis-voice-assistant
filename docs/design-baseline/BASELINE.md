# Jarvis — Visuelle Baseline (Phase 0)

**Stand:** 2026-07-11 · Arbeitsstand auf `master` (HEAD `dd43a62` + 45 uncommittete Änderungen des Nutzers — die Baseline dokumentiert den **Arbeitsstand**, nicht HEAD).
**Zweck:** Vollständige Dokumentation des visuellen und funktionalen Ist-Zustands vor dem Redesign. Jede spätere Änderung muss sich objektiv gegen diese Baseline vergleichen lassen. In Phase 0 wurde **keine produktive Datei verändert** — alle Artefakte liegen unter `docs/design-baseline/`.

**Aufnahme-Umgebung:** Windows 11, Python 3.14.5, Playwright-Chromium (headless), 2 physische Monitore à 1920×1080 (erscheinen real in der Monitor-Map). Server: Baseline-Harness auf Port **8341** mit Dummy-Keys, LLM-/TTS-/App-Start-Stubs — **kein einziger externer API-Call** (Server-Log: ausschließlich `127.0.0.1`).

---

## 1. Untersuchte Dateien und Ansichten

**Code:** `frontend/index.html` (236 Z.), `frontend/main.js` (1635 Z.), `frontend/settings.js` (169 Z.), `frontend/music.js` (102 Z.), `frontend/style.css` (2070 Z.), `jarvis-launcher.pyw` (486 Z.), `server.py`, `assistant_core.py`, `config_loader.py`, `actions.py`, `app_launcher.py`, `tts.py`, `memory.py`, `monitors.py`, `health.py`, `FEATURES.md`, `scripts/smoke-test.py`, komplette `tests/`-Suite (21 Dateien).

**Im Browser geprüfte Ansichten:** Jarvis Vollbild / Fokus („Mitte") / Panel („Klein") · Kontrollzentrum Übersicht (Fokus + Vollbild) · Einstellungen · Musik · Monitor-Map (inkl. Hover-Ghost, Ladezustand) · Transcript mit 7 Nachrichten + Suche · Aktionshistorie (Kontrollzentrum + Panel) · App-Module + Profil-Leiste.

## 2. Screenshot-Verzeichnis

Ort: `docs/design-baseline/screenshots/` (27 PNGs). Reproduktion: siehe §11. „erzwungen" = über öffentliche Client-API (`setOrbState`, `showErrorBanner`, `addActionEntry`) bzw. angehaltenen Request — identische CSS-Klassen wie im echten Flow, keine Logikänderung.

| Datei | Zustand | Methode |
|---|---|---|
| jarvis--fullscreen--idle.png | Grundzustand nach Begrüßung | echt |
| jarvis--fullscreen--listening-forced.png / -ptt-real.png | Zuhören (erzwungen / real per Space-PTT) | beide |
| jarvis--fullscreen--thinking-forced.png | Denken | erzwungen |
| jarvis--fullscreen--speaking-forced.png | Sprechen | erzwungen (s. §9) |
| jarvis--fullscreen--error-forced.png | Fehler-Orb | erzwungen |
| jarvis--fullscreen--muted-real.png · jarvis--panel--muted.png | Stumm (roter Ring, „MIKROFON STUMM") | echt (Mute-Button) |
| jarvis--fullscreen--error-banner.png | TTS-Fehlerbanner oben rechts | erzwungen |
| jarvis--fullscreen--empty-disconnected.png | Leeres Transcript + „GETRENNT" + Reconnect-Status | echt (WS im Testbrowser geblockt) |
| jarvis--fullscreen--transcript-multi.png / -search.png | 7 Nachrichten / Suche „Orb" filtert | echt (LLM-Stub) |
| jarvis--fullscreen--hover-copy-button.png | Hover zeigt Kopieren-Button | echt |
| jarvis--fullscreen--keyboard-focus.png | Fokus nach 3×Tab auf `#mute-btn` — **nicht erkennbar** | echt |
| jarvis--fullscreen--reduced-motion-listening.png | reduced-motion: Orb pulsiert weiter (Lücke) | echt (emulate_media) |
| jarvis--focus--actions.png | Jarvis-Seite im Fokus-Fenster — **ohne** Aktionsliste (s. §6) | echt |
| jarvis--panel--answer-actions.png | Panel: Mini-Antwort, Musik-Status, Mini-Aktionshistorie | echt + injizierte Einträge |
| control-overview--focus--default.png | Kontrollzentrum 1000×800 (Aktionen-Liste kollabiert!) | echt |
| control-overview--fullscreen--default.png | Kontrollzentrum 1920×1080 (Aktionen sichtbar, Heute-Leerzustände) | echt |
| control-overview--focus--map-hover.png / --map-loading.png | Zonen-Ghost / „Lade Monitore…" | echt / Request angehalten |
| control-overview--focus--app-selected.png / --app-open-feedback.png | App gewählt (Zuweisungsmodus) / Öffnen-Feedback | echt (Starts gestubbt) |
| control-overview--focus--keyboard-focus.png | Tab-Fokus im Kontrollzentrum | echt |
| control-settings--focus--default.png | Einstellungen (Temp-Pfade, PTT gewählt) | echt |
| control-music--focus--list.png / --selected.png | Musikliste / Auswahl markiert | echt (POST in Temp-Config) |

## 3. Farben, Typografie, Oberflächen

**Zentrale Erkenntnis: Es gibt kein Token-System.** `style.css` (2070 Zeilen) enthält **null** CSS-Custom-Properties; jede Farbe/Größe ist hartkodiert. Organisation über `── … ──`-Kommentarbanner, Media-Queries bewusst am Dateiende.

**Palette (wiederkehrende Hex-Werte):**
- Basis: Hintergrund `#0d0b09` (warmes Fast-Schwarz), Primärtext `#c4b49a`.
- Braun-Rampe (Labels/gedämpft): `#7a5c38`, `#6a5030`, `#5a4630`, `#4a3826`, `#3a2e22`, `#3e3026`, `#2a1e12`.
- Gold/Amber-Akzente: `#b08850` (Primärakzent), `#d4a032` (hell/aktiv), `#b6832f`, `#8a6030`, `#a08060`, `#c07830`; Tray-Icon `#c8922a`/`#e8b84b` (launcher.pyw).
- Feedback: Fehler `#c06060`/`#c05050`, Erfolg `#8fa35c`.
- Alpha-Familien (Borders/Glows/Grid): `rgba(200,155,70,α)`, `rgba(220,170,55,α)`, `rgba(190,55,45,α)`.
- Orb-Gradients je Zustand (style.css 309–388): idle `#2e1e0c→#130d07`, listening `#c07830→#6e3e12`, thinking `#d4a032→#7c5a18`, speaking `#c87840→#6e3e1c`, muted `#241a10→#100c08` + roter Ring, error `#7c2a20→#2a0f0a`.

**Typografie:** Systemstack `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`, keine Webfonts. Grundgewicht 300. Größen 8–13 px (Orb-Status 10 px, Transcript Du 11 px / Jarvis 13 px, Zeitstempel 9 px). Markenzeichen: `text-transform: uppercase` + `letter-spacing` 0.08–0.28 em auf fast allen Labels/Buttons.

**Oberflächen:** Border-Radien 3/4/5/6/7 px + 50 % (Orb, Dots, Toggle). Geschichtete `box-shadow`-Glows (Orb, Status-Dots, Chips, selected). Zwei fixe „Lamp-Glows" via `body::before/::after` (unten rechts sichtbar). Feine Amber-Grid-Linien im Kontrollzentrum.

**Keyframes:** `pulse-listen` 1.8 s, `pulse-think` 0.85 s, `pulse-speak` 0.65 s, `flash-error` 1.1 s ×2, `banner-in` 0.25 s, `map-pulse` 0.6 s.

**Maße:** Win-Bar 38 px; Orb 160/96/72 px (Vollbild/Fokus/Panel); Buttons 34 px; rechte CC-Spalte 250 px; Fokus-Konversationsspalte 340 px.

## 4. Komponenten und Interaktionsmuster

- **Routing = Klassenstring** auf `<html>` via `rootClass()` (main.js 151–158): `page-jarvis mode-fullscreen` · `page-jarvis` (Fokus) · `page-jarvis mode-panel` · `mode-focus [mode-fullscreen] page-control cc-view-<overview|settings|music>`. Kein URL-Routing, kein localStorage — Start immer Vollbild/Jarvis. `page-jarvis`/`page-control` sind reine Marker; **das Kontrollzentrum-Layout hängt komplett an `html.mode-focus`**.
- **Orb** (`#orb`, Klasse = Zustand) + Statuszeile + Status-Center (`SERVER/MIKRO/ZUSTAND` + letzter Fehler) als redundantes Signalpaar.
- **Fehlerbanner-Stack** oben rechts: `component`-Label + Text + Hinweis + ×; persistent für kritische Komponenten, sonst 10 s; `llm`/`ws` lösen zusätzlich Orb-Blitz aus.
- **Transcript:** max 20 Einträge, `Du:`/`Jarvis:`-Präfix, Zeitstempel, Kopieren einzeln (Button erst bei Hover sichtbar, `visibility:hidden` → `.msg:hover`) + „Alles kopieren", Suchfeld filtert Anzeige und Kopie. Panel spiegelt die letzte Antwort in `#panel-answer`.
- **Texteingabe:** nur Strg+Enter sendet (Enter tut nichts — dokumentiertes Verhalten).
- **Aktionshistorie:** `li.ae` mit Dot (run=pulsierend gold, ok=gold, err=rot), Zeit, Label, Detail; max 15; WS-`action`-Frames schließen jüngsten offenen Eintrag gleichen Typs.
- **Kontrollzentrum (Übersicht):** 3 Spalten — links Konversation (Mini-Orb + Transcript + Eingabe), Mitte Profil-Leiste (Tabs + Neu/Duplizieren/Umbenennen/Löschen mit Bestätigungsklick) + Monitor-Map + „Heute"-Strip (Aufgaben/Inbox/Zuletzt), rechts Apps + Aktionen + System (Dots für KI/Sprachausgabe/Browser/Vault + „Daten laden…").
- **Monitor-Map:** echte Monitore (ctypes) mit Label + Auflösung, 3×3-Zonenraster + Vollbild-Button, Hover-Ghost, Chips für Autostart-Apps je Zone, Klick-zu-Zuweisen-FSM (App wählen → Zone klicken → POST placement, Puls-Bestätigung), Drag&Drop als Enhancement, Escape bricht ab.
- **App-Module:** Name + Typ-Tag (App/URL), Öffnen-Button (busy→ok/err-Flash), Autostart-Switch (`role=switch`), Placement-Label.
- **Musik:** Ordnerpfad + Auswahl-Status, Liste (`.music-item.selected` heller Rahmen), Auswahl entfernen / Neu laden; nur Dateinamen über die API.
- **Einstellungen:** Whitelist-Textfelder, Apps-Textarea („Name = Befehl"), Mikrofonmodus-Radios (nur localStorage), Diff-only-POST; Hinweis „API-Keys … nur in config.json".
- **WS-Frames:** `response`(text+audio) · `status` · `health` · `stop` · `action` · `app_event` · `launcher_changed` · `music_changed` · `error`(component/text/hint).

## 5. Visuelle Stärken (erhaltenswert)

1. **Unverwechselbare Amber-HUD-Identität** — warmes Monochrom statt generischem Blau/Neon; wirkt wie ein physisches Gerät, nicht wie eine Website.
2. **Der Orb als lebendes Statusinstrument:** sechs klar unterscheidbare Zustände über Farbe *und* Pulsfrequenz (ruhig 1.8 s beim Zuhören, nervös 0.85 s beim Denken, sprechrhythmisch 0.65 s); der rote Muted-Ring ist sofort lesbar.
3. **Atmosphärische Tiefe** durch die Lamp-Glows und geschichtete Schatten — der Screen hat einen Lichtraum, kein flaches Dark-Theme.
4. **Konsequente Mikrotypografie** (Uppercase + weite Laufweite) als durchgängiges Markenzeichen bis in Tray und Panel.
5. **Konsistente Feedback-Sprache:** Dot+Glow-Semantik (gold=ok, pulsierend=läuft, rot=Fehler) identisch in Status-Center, Aktionshistorie, System-Liste und Map-Chips.
6. **Panel-Modus ist exzellent verdichtet** — Orb, Antwort, Musik-Status, Mini-Historie und Controls funktionieren auf 420×560 ohne Gedrängel.

## 6. Inkonsistenzen und Designschulden

1. **Kein Token-Layer** — die größte strukturelle Schuld: jede Farb-/Abstandsänderung erfordert Massen-Edits in 2070 Zeilen; nahe Goldtöne (`#b08850` vs `#d4a032` vs `#b6832f`) ohne dokumentierte Semantik.
2. **Extrem niedriger Kontrast als Systemrisiko:** inaktive Nav-/Moduswechsel-Buttons, Platzhalter („Verlauf durchsuchen…", „Nachricht tippen…"), Zeitstempel (`#3a2e22` auf `#0d0b09`) und Detail-Texte sind am Rand der Wahrnehmbarkeit (in den Screenshots teils kaum auffindbar). Exakte WCAG-Messung = Phase-1-Aufgabe.
3. **Stale Status-Text:** Nach einer Antwort **ohne Audio** bleibt „JARVIS DENKT NACH…" unter dem Orb stehen (der No-Audio-Zweig in `ws.onmessage` räumt `status` nicht auf; nur der Audio-Pfad via `playNext` tut es). Sichtbar in transcript-multi/keyboard-focus-Shots.
4. **„Letzter Fehler" im Status-Center bleibt für immer** (auch nach Banner-Dismiss) und wird unschön mittig trunkiert: „SPRACHAUSGABE FEHLGESCHLAGEN — ANTWORT WIR…".
5. **Aktionen-Liste kollabiert bei 1000×800 auf 0 Höhe:** In `#cc-right` verdrängen 4 App-Module + System-Block die Liste (`flex:1` + `min-height:0` + `overflow:hidden`) — Einträge existieren im DOM, sind aber unsichtbar (Vergleich der beiden control-overview-Shots).
6. **Aktionshistorie erscheint auf der Jarvis-Seite im Fokus-Fenster gar nicht** (Root-Klasse dort nur `page-jarvis`; `#action-history` braucht `mode-focus`=Kontrollzentrum oder `mode-panel`) — weicht von der FEATURES.md-Formulierung „Aktionshistorie im Fokus-Modus" (#26) ab.
7. **Kopieren nur per Maus-Hover entdeckbar** (`visibility:hidden`) — per Tastatur/Touch unerreichbar.
8. **Radius- (3–7 px) und Fontgrößen-Wildwuchs (8–13 px)** ohne Stufenlogik.
9. **Monitor-Map-Labels trunkieren** schon bei 1000×800 („LINKER MONITOR …").
10. **„Daten laden…"** im System-Block hat keinen Fehler-/Endzustand, wenn der Refresh nie abschließt.

## 7. Accessibility- und Responsive-Auffälligkeiten

- **Kein `:focus-visible` im gesamten CSS**; verbreitet `outline:none` + Border-Farbwechsel. Belegt: Nach 3×Tab liegt der Fokus auf `#mute-btn`, im Screenshot ist **kein** Fokusindikator erkennbar.
- **`prefers-reduced-motion` deckt nur Map/App-Module/Profil-/Tab-Transitions ab** (style.css 1972–1988) — Orb-Pulse, `flash-error`, `banner-in` und die Lamp-Glows laufen weiter (Screenshot reduced-motion-listening: Puls aktiv).
- **Positiv:** durchgängig `aria-live` auf Statusflächen, `role=tablist/tab/tabpanel`, `role=group`, `role=switch`+`aria-checked`, `aria-pressed`/`aria-selected` JS-gepflegt, `aria-label` auf Map-Zonen, `lang="de"`, Boot-Fallback mit `aria-live`, Enter/Space-Aktivierung auf Modulen/Zonen, Escape-Capture-Logik.
- **Responsive:** Degradations-Queries bei 1100/960/700 px (am CSS-Ende, überschreiben Fokus-Regeln); Panel 420×560 sehr gut; kritisch ist die **Höhe** (Aktionen-Kollaps bei 800 px, s. §6.5).
- Kleinere Punkte: Titelbar-Buttons (−/×) ohne sichtbaren Fokus; Suchfeld/Editfelder mit sehr niedrigem Platzhalterkontrast; Fokusreihenfolge folgt DOM (Nav → Fenstermodus → Mute/Stop → Inhalt).

## 8. Funktionale Invarianten (das Redesign darf sie nicht verändern)

1. **WS-Sicherheit:** `/ws` nur mit `?token=` (Session-Token, per `GET /` in die Seite injiziert, `secrets.compare_digest`) **und** erlaubtem Origin (`http/https` mit Host `localhost`/`127.0.0.1`/`::1`, portunabhängig; Origin `"null"` nur mit gültigem Token; sonst Close 1008). REST verlangt `X-Jarvis-Token`. API-Keys erreichen nie das Frontend; `POST /settings` lehnt Key-Felder ab.
2. **Auto-Begrüßung:** Beim ersten WS-Connect sendet der Client einmalig `'Jarvis activate'` (löst LLM+TTS und `refresh_data` aus — kostenrelevant! Bei UI-Tests immer Stub-Harness §11 verwenden). Kein erneutes Greeting bei Reconnect.
3. **Stopp:** Stop-Button, **Escape** und Stop-Wörter → lokales Stoppen der Wiedergabe + `{type:'stop'}` (bricht Serverseitig laufende Aktion ab). Capture-Phase-Escape bricht zuerst App-Auswahl/Profil-Löschmodus ab (stopImmediatePropagation).
4. **Mute:** betrifft nur Mikro/Orb-Anzeige, nicht Texteingabe; Erkennung läuft stumm weiter (Sprach-Entstummen möglich); Zustände `muted`-Orb + roter Button + „STUMM" im Status-Center.
5. **Moden-Kontrakt:** Root-Klassenstrings exakt wie in §4; `applyUiMode/applyAppPage/applyControlView` + pywebview-Guards; Start-Zustand Vollbild/Jarvis; Kontrollzentrum reitet immer auf `mode-focus`.
6. **Transcript:** max 20, Präfixe, Zeitstempel `de-DE`, Suche filtert Anzeige und „Alles kopieren", Einzelkopie mit Fallback (`execCommand`) + copied-Flash, Panel-Spiegel.
7. **Settings/Musik:** Whitelist + Diff-only-POST; Musik nur Dateinamen, `music_changed`-Push aktualisiert Liste und „Nächste Musik"-Status.
8. **Launcher:** Profile (Neu/Duplizieren/Umbenennen/Löschen mit Bestätigung, Aktivieren), Autostart-Toggle, Placement über Map (Monitor+Zone, Geometrie synchron zu `launch-session.ps1`), App-Öffnen nur über `POST /commands/app/open` gegen die `config.apps`-Allowlist.
9. **Aktionshistorie:** `action`-Frames (start/done/error) wie in §4; max 15; Sichtbarkeit Kontrollzentrum + Panel (Mini ~3).
10. **Tastatur:** Strg+Enter sendet, Enter nicht; Space = PTT außerhalb von Eingabefeldern; Enter/Space aktivieren Module/Zonen; Orb-Klick toggelt Zuhören; Mikrofonmodi auto/ptt/off via localStorage.
11. **Offline-Verhalten:** Exponentieller Reconnect 3 s→30 s, „GETRENNT" im Status-Center, ws-Banner erst beim 3. Versuch, Mikro bleibt nutzbar.
12. **Fehlerbanner:** strukturiert (component/text/hint), persistent vs. 10 s-Auto-Dismiss, `llm`/`ws` → Orb-Blitz; Boot-Fallback (`jarvisBootFail`) + `body.jarvis-ready`-Gate.
13. **`prefers-reduced-motion`:** bestehende Abdeckung ist Minimum — darf nur wachsen.

## 9. Nicht prüfbare Zustände und offene Voraussetzungen

| Nicht geprüft | Grund | Sichere spätere Prüfung |
|---|---|---|
| Echtes `speaking` mit Audio | TTS-Stub liefert kein Audio; leeres Audio überspringt den Speaking-Pfad (main.js `playNext`) | Harness-Stub eine kurze echte MP3 zurückgeben lassen — weiterhin ohne ElevenLabs |
| Echte Spracherkennung/Dauerzuhören (`auto`-Modus) | Playwright-Chromium hat keinen Google-Speech-Dienst; Aufnahme lief deterministisch in `ptt` | Manuell in installiertem Chrome gegen das Harness (Port 8341) |
| Natives Fenster: Mica, Tray, Win+J, echte Panel-/Fokus-Platzierung, Fenster-Buttons | pywebview-API im Browser No-Op | `jarvis-launcher.pyw` manuell starten (JARVIS_DEBUG/NO_*-Flags vorhanden) |
| Doppelklatschen + Session-Start | startet echte Apps (launch-session.ps1) | separater überwachter Lauf; nicht Teil der UI-Baseline |
| Echte Aktionen (RESEARCH/Browser/Vision) | externe Calls bzw. echter Browser | Aktions-UI wurde über injizierte `action`-Frames dokumentiert; Flows sind durch `tests/test_integration_research.py` abgedeckt |
| Animations-**Verläufe** (Puls, Banner-Slide, Map-Puls) | PNG = Standbild | Bei Bedarf in Phase 1 kurze Videoaufnahme (Playwright `record_video`) über dasselbe Harness |
| `auto`-Mikrofonmodus im Settings-Screenshot | Aufnahme nutzte `ptt` (s. o.) | rein visuell identisch bis auf Radio-Auswahl |

## 10. Testergebnisse (frische Evidenz, 2026-07-11)

| Befehl | Exit-Code | Ergebnis |
|---|---|---|
| `python -m unittest discover -s tests -v` | **0** | **471 Tests, 0 Failures, 0 Errors, 0 Skips** (2.4 s) |
| `python scripts/smoke-test.py` | **0** | Alle Schritte ✓: Dependencies (6 Pakete) · config.json gültig · alle Modul-Imports · In-Process-Server `/health` „alle Dienste ok" · Testsuite 471/0/0 |

Keine fehlenden Abhängigkeiten. Beide Läufe vollständig offline (LLM/TTS/Browser in Tests gemockt; Smoke-Test nutzt `TestClient` ohne Port und `JARVIS_SKIP_STARTUP_REFRESH=1`). Hinweis: `tests/test_frontend.py` enthält statische Text-Guards über die Frontend-Dateien — beim Redesign zuerst dort mit Regressionen rechnen.

## 11. Reproduktion der Baseline

```powershell
# 1) Harness (echter Server, Port 8341, Dummy-Keys, LLM/TTS/App-Starts gestubbt)
python docs/design-baseline/tools/baseline_server.py

# 2) Screenshot-Matrix (zweites Terminal; überschreibt screenshots/ deterministisch)
python docs/design-baseline/tools/capture_baseline.py
```

Wichtig: Die UI **niemals** gegen `python server.py` (Port 8340, echte config.json) automatisiert öffnen — die Auto-Begrüßung (§8.2) löst sonst echte Anthropic-/ElevenLabs-Calls aus. Für Redesign-Vergleiche denselben Capture-Lauf wiederholen und PNGs diffen; Harness vor jedem Lauf frisch starten (setzt die zyklischen Stub-Antworten zurück, hält Transcript-Inhalte identisch).
