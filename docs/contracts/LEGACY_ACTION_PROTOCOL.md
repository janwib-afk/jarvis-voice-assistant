# Jarvis – Legacy-Action-Protokoll (`[ACTION:...]`, Ist-Zustand)

> Dokumentiert das **aktuelle** Text-Action-Protokoll (`actions.py`,
> Ausführung seit RFC-0001 je Action an ihrem Registry-Eintrag, `actions.py`:
> `spec.execute(payload, ctx)`; `assistant_core.execute_action` ist nur noch der
> kompatible Thin Dispatcher). Stand 2026-07-15. Dies ist ein
> **Legacy-Vertrag**: die LLM-Ausgabe kodiert Aktionen als Text-Tags. Er wird in
> Prompt 6 **nicht** geändert, nicht erweitert und nicht entfernt. Bezug:
> [../quality/TEST_SEAMS.md](../quality/TEST_SEAMS.md) (SEAM-ACTION),
> RFC-0001 (Action → deep module).

## Format

```
<gesprochener Text>[ACTION:TYPE] <payload bis Zeilenende>
```

- Regex: `\[ACTION:(\w+)\]\s*(.*?)$` mit `DOTALL|MULTILINE`
  (`actions.ACTION_PATTERN`).
- **Maximal eine Aktion** pro Antwort; der Text **vor** dem Tag wird vorgelesen,
  der Tag selbst wird still ausgeführt.
- `parse_action(text)` → `(spoken_text, Action|None, error|None)`
  (`actions.py:210`). `Action` ist ein `frozen dataclass` `{type, payload}`.
- `TYPE` wird `upper()`-normalisiert; Payload wird `.strip()`-t.

## Registrierte Action-Typen (22)

Nur in `actions.REGISTRY` eingetragene Typen werden geparst/ausgeführt.
Payload: `req` = Pflicht, `opt` = optional, `none` = wird verworfen.

| # | TYPE | Label | Payload | URL | Risk | Timeout (s) | speaks_result | Ausführung (`spec.execute`) |
|---|---|---|---|---|---|---|---|---|
| 1 | `SEARCH` | Websuche | req | – | low | 60 | – | `browser_tools.search_and_read` |
| 2 | `BROWSE` | Seite lesen | req | ✓ | low | 60 | – | `browser_tools.visit` |
| 3 | `OPEN` | Browser öffnen | req | ✓ | low | 60 | – | `browser_tools.open_url` (keine Zusammenfassung) |
| 4 | `APP_OPEN` | App öffnen | req | – | low | 15 | ✓ | `app_launcher.launch` (Allowlist) |
| 5 | `PROFILE_ACTIVATE` | Profil aktivieren | req | – | low | 15 | ✓ | Profil-Schicht (`_exec_profile_activate`) |
| 6 | `PROFILE_STATUS` | Profil-Status | opt | – | low | 15 | ✓ | `_exec_profile_status` |
| 7 | `APP_AUTOSTART_ON` | Clap-Start an | req | – | low | 15 | ✓ | `_exec_autostart_on` |
| 8 | `APP_AUTOSTART_OFF` | Clap-Start aus | req | – | low | 15 | ✓ | `_exec_autostart_off` |
| 9 | `APP_PLACE` | App platzieren | req | – | low | 15 | ✓ | `_voice_place_app` (`app \| monitor \| zone`) |
| 10 | `SCREEN` | Bildschirm ansehen | opt | – | low | 60 | – | `screen_capture.describe_screen` (Vision) |
| 11 | `NEWS` | Nachrichten | none | – | low | 60 | – | `browser_tools.fetch_news` |
| 12 | `INBOX_READ` | Inbox lesen | none | – | low | 60 | – | `memory.read_today_inbox_sync` |
| 13 | `INBOX_WRITE` | Inbox-Eintrag | req | – | low | 60 | – | `memory.write_inbox_entry` (Kategorie aus `[…]`) |
| 14 | `MEMORY_WRITE` | Merken | req | – | low | 60 | – | `memory.append_memory` |
| 15 | `MEMORY_READ` | Gedächtnis lesen | none | – | low | 60 | – | `memory.read_memory_sync` |
| 16 | `MEMORY_FORGET` | Vergessen | req | – | **confirm** | 60 | – | `memory.forget_memory` (**erst nach mündlichem Ja**) |
| 17 | `RESEARCH` | Recherche | req | – | low | **180** | – | `run_research` (3–5 Quellen) |
| 18 | `CLIPBOARD` | Zwischenablage | opt | – | low | 60 | – | `clipboard_tools.get_clipboard_text` + Auftrag |
| 19 | `CLIPBOARD_NOTE` | Clipboard-Notiz | none | – | low | 60 | – | Clipboard → `memory.write_inbox_entry` |
| 20 | `NOTES_RECENT` | Letzte Notizen | none | – | low | 60 | – | `memory.read_recent_notes_sync` |
| 21 | `PROJECT_CONTEXT` | Projekt-Kontext | req | – | low | 60 | – | `memory.get_project_context_sync` (lokale Vault-Suche) |
| 22 | `SESSION_SUMMARY` | Sitzungsfazit | none | – | low | 60 | – | Verlauf der Session zusammenfassen |

(`is_browser=True` für SEARCH/BROWSE/OPEN/NEWS/RESEARCH → Fehler werden als
`component:"browser"` gemeldet.)

## Payload-Regeln

- `none`-Actions: ein mitgegebener Payload wird **verworfen** (`payload=""`).
- `optional`-Actions: leerer Payload ist erlaubt (z.B. `SCREEN` ohne Kontextfrage).
- `required`-Actions: fehlt der Payload → `error = "fehlender Payload fuer TYPE"`,
  keine Ausführung.
- `INBOX_WRITE`: führendes `[Kategorie]` wird via `split_inbox_category` erkannt
  (Kategorien: Idee, Aufgabe, Termin, Recherche, Erinnerung; sonst Fallback
  „Notiz"). Es geht nie Text verloren.
- `APP_PLACE`: Payload `app | monitor | zone` via `parse_place_payload`; Monitor/
  Zone gegen Allowlists (deutsche Aliasse werden auf kanonische Werte gemappt).

## URL-Normalisierung (`normalize_url`, `actions.py:171`)

- Für `is_url`-Actions (BROWSE, OPEN): fehlt das Schema, wird `https://`
  vorangestellt (LLM liefert oft bare Domains).
- Erlaubt sind **ausschließlich** `http` und `https`. `javascript:`, `file:`,
  `data:`, `mailto:` u.ä. werden abgelehnt → `error = "ungueltige URL fuer TYPE"`.
- Eine Authority (netloc) muss vorhanden sein.
- **Sicherheitsgrenze (bekannt):** aktuell wird nur das **Schema** geprüft, nicht
  der Zielhost — SSRF gegen loopback/RFC1918/link-local/metadata bleibt möglich
  (Threat **TM-002**, Mitigation geplant Phase 5).

## Risk / Bestätigung

- `MEMORY_FORGET` hat `risk="confirm"` → `CONFIRM_ACTIONS`. Die Verarbeitung meldet die
  Rückfrage über `ctx.request_confirmation(action)` an den Session-Zustand und stellt eine
  mündliche Rückfrage; erst die nächste Nachricht (`is_confirmation` → Ja/Nein) führt aus
  oder verwirft. Seit RFC-0006 hält die offene Rückfrage der Session-Kern (`suspended`) und
  gibt sie beim Turn-Start als `ctx.pending` **konsumiert** weiter — das frühere Modul-Global
  `assistant_core.pending_confirm` gibt es nicht mehr. Verneinung gewinnt bei Mehrdeutigkeit.
- Weitere riskante Aktionen bekommen einfach `risk="confirm"` in der Registry und
  sind damit automatisch abgesichert.

## Direkte vs. zusammengefasste Antworten

- `speaks_result=True` (`SPEAK_RESULT_ACTIONS`, alle Launcher-Actions + APP_OPEN):
  das Ergebnis ist bereits ein kurzer deutscher Satz und wird **direkt** gesprochen
  — keine LLM-Zusammenfassung.
- `OPEN`: nach dem Öffnen wird nichts zusammengefasst (nur die Browser-Aktion).
- Alle übrigen: das Ergebnis wird über ein zweites Haiku-Call zusammengefasst
  (aktionsspezifische `summary_task`/`summary_max_tokens`), dann gesprochen.
  `RESEARCH` hängt zusätzlich eine Quellenliste an die **Anzeige** (nicht die
  Sprachausgabe) und speichert das Ergebnis in die Inbox (Autosave).

## Verhalten bei unbekannten/ungültigen Tags

- Kein Tag → `(text, None, None)`; der ganze Text wird gesprochen.
- Unbekannter Typ → `(spoken, None, "unbekannter Action-Typ: TYPE")`; nur der Text
  vor dem Tag wird gesprochen, **nichts** wird ausgeführt.
- Fehlender Pflicht-Payload / ungültige URL → analog `error`, keine Ausführung.
- `process_message` loggt den `action_err` und spricht nur `spoken_text`
  (`assistant_core.py:695`).

## Stop / Cancel

- `is_stop_command` (`actions.py:378`) erkennt reine Stopp-Äußerungen (max. 5
  Wörter, Stop-Wort + nur Füllwörter). „Wie stoppe ich einen Container?" ist
  **keine** Stopp-Äußerung.
- Ein Stop bricht die laufende Aktion ab (`asyncio.CancelledError` in
  `run_action_and_respond` → `action`-Frame `phase:"error", detail:"abgebrochen"`)
  und wird an den WS-Endpunkt weitergereicht (siehe WEBSOCKET_PROTOCOL).
- Jede Aktion hat einen Gesamt-`timeout` (`asyncio.wait_for`, `assistant_core.py:597`)
  — ein hängender Browser blockiert die WS-Loop nie länger als `spec.timeout`.

## Security-Anforderungen (Zusammenfassung)

- SI-1: untrusted LLM-Ausgabe kann **nur** registrierte Actions auslösen, keine
  Wirkungsklasse erhöhen; unbekannte/ungültige Tags werden nie ausgeführt.
- SI-6: nur http/https-URLs; App-/Profil-Wirkung nur über Allowlist/Profil-Schicht,
  nie über freie Kommandos.
- SI-7: destruktive Wirkung (`MEMORY_FORGET`) nur nach mündlicher Bestätigung.

## Spätere Rolle

`parse_action` bleibt gemäß RFC-0001 ein **permanenter Adapter** von der
`[ACTION:…]`-Textform auf validierte `Action`-Records — auch wenn der Action-Kern
später zum deep module wird. Dieses Protokoll wird **nicht** entfernt und **nicht**
durch eine neue Capability-Syntax ersetzt (out of scope für Prompt 6).
