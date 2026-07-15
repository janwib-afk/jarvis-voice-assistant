# Jarvis – REST-Verträge (Ist-Zustand)

> Dokumentiert das **aktuelle** Verhalten der REST-Routen in `server.py`, nicht ein
> Zielprotokoll. Stand 2026-07-14. Alle Beispielwerte sind synthetisch. Bezug:
> [../quality/TEST_SEAMS.md](../quality/TEST_SEAMS.md) (SEAM-REST/-LAUNCHER),
> [../security/SECURITY_REQUIREMENTS.md](../security/SECURITY_REQUIREMENTS.md).

## Gemeinsame Regeln

- **Bind:** nur `127.0.0.1:8340` (`server.py:746`) — nicht im LAN erreichbar (SI-4).
- **Authentisierung (geschützte Routen):** Session-Token im Header
  `x-jarvis-token`, geprüft mit `secrets.compare_digest`
  (`server._settings_token_ok`, `server.py:236`). Fehlt/falsch → `403`
  `{"ok": false, "errors": ["Nicht autorisiert."]}`.
- **Autorisierung:** keine Rollen; das Token IST die Autorisierung (lokaler
  Einzelbenutzer, ADR 0004). Wirkende Endpunkte laufen über dieselben Allowlists
  wie die Sprach-Aktionen.
- **Fehlerform (einheitlich):** `{"ok": false, "errors": [<deutscher Text>, …]}`.
  Fehlermeldungen nennen nie Secret-Werte, nur Schlüsselnamen (SI-5).
- **Secrets:** API-Keys (`PROTECTED_KEYS`) verlassen den Server nie — weder lesbar
  (`GET /settings`) noch schreibbar (`POST /settings`).
- **JSON-Parsefehler** bei POST-Routen → `400` `{"ok": false, "errors":
  ["Ungültiges JSON."]}`.

Datenklassen/Wirkungsklassen: siehe SECURITY_REQUIREMENTS (`public/local/personal/
sensitive/secret`; `read-local/local-write/local-execute/…`).

---

## Öffentliche Routen (ohne Token)

### `GET /health`
- **Zweck:** passiver Statusbericht (Launcher/Tests/Smoke). Fragt **keine** bezahlte
  API an (kein Quota-Verbrauch).
- **Auth/Autor.:** keine.
- **Request:** keine Felder.
- **Response `200`:** `{"ok": bool, "warnings": [str], "services": {"config":
  {"ok": bool, …}, "llm": {…}, "tts": {…}, "browser": {…}, "vault": {…}},
  "startup": {"data_loaded": bool, "last_refresh": float|null}}`.
- **Statuscodes:** `200` (auch bei degradierten Diensten — `ok` bleibt true, solange
  der Server Verbindungen annimmt).
- **Wirkungsklasse:** `read-local`. **Datenklasse:** `local` (Diagnose; keine
  Secret-Werte, nur Vorhandensein/Existenz).
- **Idempotenz:** ja (read-only).
- **Security Requirements:** secret-frei; bewusst ungeschützt (Diagnosezweck).
- **Tests:** `test_ws.py::HealthEndpointTests`.

### `GET /`
- **Zweck:** liefert die UI (`frontend/index.html`) und injiziert das Session-Token
  als `window.JARVIS_TOKEN` (Same-Origin, `server.py:723`).
- **Auth/Autor.:** keine (die Same-Origin-Policy schützt das injizierte Token).
- **Response `200`:** `text/html`.
- **Wirkungsklasse:** `read-local`. **Datenklasse:** `secret` (enthält das Token) —
  siehe Threat TM-003 (lokaler Prozess kann das Token via `GET /` lesen).
- **Idempotenz:** ja.
- **Tests:** —(indirekt über WS-Handshake, der das Token nutzt).

### `/static/*`
- **Zweck:** statische Frontend-Assets (`StaticFiles`, `server.py:214`).
- **Datenklasse:** `public`. **Wirkungsklasse:** `read-local`.

---

## Geschützte Routen (Token-Pflicht)

Alle folgenden Routen antworten `403` ohne gültiges `x-jarvis-token`.

### `GET /settings`
- **Zweck:** UI-editierbare Settings + Startwarnungen lesen.
- **Response `200`:** `{"ok": true, "settings": {<UI_EDITABLE_KEYS>}, "warnings":
  [str]}`. `settings` enthält nur die Whitelist (`config_loader.UI_EDITABLE_KEYS`),
  **nie** API-Keys.
- **Wirkungsklasse:** `read-local`. **Datenklasse:** `personal` (Name/Rolle/Stadt/
  Pfade).
- **Idempotenz:** ja.
- **Security Requirements:** SI-5 (keine Secrets); Whitelist.
- **Tests:** `test_settings_api.py`.

### `POST /settings`
- **Zweck:** UI-editierbare Felder validieren, atomar speichern, live anwenden.
- **Request:** JSON-Objekt aus `UI_EDITABLE_KEYS` (z.B. `{"city": "Beispielstadt",
  "user_address": "Chef"}`).
- **Response `200`:** `{"ok": true, "applied": [<sortierte Keys>], "warnings":
  [str]}`.
- **Statuscodes:** `200` ok; `400` Validierungsfehler oder ungültiges JSON; `403`
  ohne Token; `500` Schreibfehler (`ConfigError`, nur Schlüsselnamen).
- **Validierung:** `config_loader.validate_settings_update` — geschützte Keys
  abgelehnt (`'anthropic_api_key' kann nur direkt in config.json geändert
  werden.`), unbekannte Keys abgelehnt.
- **Wirkungsklasse:** `local-write` (`config.json`). **Datenklasse:** `personal`.
- **Idempotenz:** ja (gleicher Body → gleicher Zustand; Merge, kein Append).
- **Security Requirements:** SI-5, `PROTECTED_KEYS`, atomarer Schreibpfad
  (`.tmp` → `os.replace`) bewahrt Secrets/unbekannte Felder.
- **Tests:** `test_settings_api.py`, `test_config.py` (Persistenz).

### `GET /music/files`
- **Zweck:** `.mp3`-Liste des konfigurierten Musikordners + aktuelle Auswahl.
- **Response `200`:** `{"ok": bool, "folder": str, "selected": str, "files":
  [{"name": str, "size": int|null, "modified": float|null}], "error": str}`.
  `ok:false` mit `error` bei fehlendem/unlesbarem Ordner — **trotzdem HTTP 200**
  (Zustandsbericht, kein Crash).
- **Wirkungsklasse:** `read-local`. **Datenklasse:** `local` (Dateinamen/Pfad).
- **Idempotenz:** ja.
- **Tests:** `test_music_api.py`.

### `POST /music/selection`
- **Zweck:** `.mp3` für den nächsten Sessionstart wählen (`""` = abwählen).
- **Request:** `{"file": "beispiel.mp3"}`.
- **Response `200`:** `{"ok": true, "selected": str}`; zusätzlich WS-Broadcast
  `{"type": "music_changed", "selected": str, "ts": float}`.
- **Statuscodes:** `200`; `400` (Feld fehlt / ungültiger Dateiname / Ordner fehlt /
  Datei nicht gefunden); `403`; `500` (`ConfigError`).
- **Validierung:** `validate_music_file_value` — reiner `.mp3`-Dateiname, kein Pfad
  (kein `/ \ : ..`), + Existenzprüfung im Ordner (Defense-in-Depth).
- **Wirkungsklasse:** `local-write`. **Datenklasse:** `local`.
- **Idempotenz:** ja.
- **Tests:** `test_music_api.py`.

### `GET /dashboard/state`
- **Zweck:** Daten für das Command Center (Fokus-Modus).
- **Response `200`:** `{"ok": true, "health": {…}, "tasks": [str], "today_inbox":
  str|null, "vault": {…}|null, "apps": [<effective apps>], "data_loaded": bool,
  "last_refresh": float|null}`. Nutzt gecachte Kontextdaten (kein Vault-Scan pro
  Aufruf).
- **Wirkungsklasse:** `read-local`. **Datenklasse:** `personal` (Tasks/Inbox/Vault).
- **Idempotenz:** ja.
- **Tests:** `test_dashboard_api.py`.

### `POST /commands/app/open`
- **Zweck:** App aus der Registry starten (UI-Klick) — gleiche Allowlist wie
  `[ACTION:APP_OPEN]`.
- **Request:** `{"app": "Beispiel-App"}`.
- **Response:** `{"ok": bool, "app": str|null, "name": str|null, "message": str}`;
  WS-Broadcast `{"type": "app_event", …}`.
- **Statuscodes:** `200` (Start ok), `404` (App unbekannt → `app` ist null), `500`
  (Start fehlgeschlagen), `400` (Feld `app` fehlt), `403`.
- **Wirkungsklasse:** `local-execute`. **Datenklasse:** `local`.
- **Idempotenz:** nein im engeren Sinn (jeder Aufruf startet die App erneut) — aber
  ausschließlich Allowlist-Apps, nie freie Kommandos.
- **Security Requirements:** nur `app_launcher.launch` (Allowlist), keine Shell.
- **Tests:** `test_dashboard_api.py`.

### Launcher- und Profil-Routen

Alle Profil-Antworten nutzen die einheitliche Form
`_profiles_response()`: `{"ok": true, "active_profile": str, "profiles":
[{"id","name","apps"}], "apps": [<effective apps>]}`.

| Route | Zweck | Request | Erfolg | Fehler | Wirkung | Idempotent |
|---|---|---|---|---|---|---|
| `GET /launcher/apps` | effektive Apps des aktiven Profils | — | `{ok, active_profile, apps}` | `403` | read-local | ja |
| `POST /launcher/apps/{app_id}/toggle` | Autostart setzen (expliziter Bool) | `{"autostart": true}` | `{ok, apps}` | `400` (kein Bool), `404` (App), `403`, `500` | local-write | **ja** (expliziter Wert, kein Flip) |
| `GET /launcher/monitors` | physische Monitore | — | `{ok, monitors:[…]}` (leer = Erkennung fehlgeschlagen) | `403` | read-local | ja |
| `POST /launcher/apps/{app_id}/placement` | Monitor/Zone setzen | `{"monitor":"left","zone":"right_half"}` | `{ok, apps}` | `400` (Feld fehlt/ungültig), `404`, `403`, `500` | local-write | **ja** (beide Felder Pflicht) |
| `GET /launcher/profiles` | Profile + effektive Apps | — | `_profiles_response` | `403` | read-local | ja |
| `POST /launcher/profiles` | Profil anlegen (Defaults; aktiviert NICHT) | `{"name":"Beispiel","id?":"beispiel"}` | `_profiles_response` | `400` (Name fehlt / ID vergeben), `403`, `500` | local-write | nein (Anlegen) |
| `POST /launcher/profiles/{id}/activate` | aktives Profil wechseln | — | `_profiles_response` | `404`, `403`, `500` | local-write | ja |
| `POST /launcher/profiles/{id}/duplicate` | Profil kopieren | `{"name":"Kopie","id?":…}` | `_profiles_response` | `404` (Quelle), `400` (Name/ID), `403`, `500` | local-write | nein |
| `POST /launcher/profiles/{id}/rename` | Profil umbenennen (ID stabil) | `{"name":"Neu"}` | `_profiles_response` | `404`, `400`, `403`, `500` | local-write | ja |
| `DELETE /launcher/profiles/{id}` | Profil löschen | — | `_profiles_response` | `400` (letztes/aktives Profil geschützt), `404`, `403`, `500` | local-write | ja (löschen) |

- **Datenklasse (Launcher/Profile):** `local` (App-IDs, Profilnamen, Monitor/Zone
  sind Allowlist-Konstanten oder Nutzer-Labels).
- **Security Requirements:** Cross-Check gegen App-Registry
  (`validate_launcher_value(app_ids=…)`); Monitor/Zone gegen Allowlists; `command`
  verlässt den Server nie.
- **Tests:** `test_launcher_api.py`.

---

## Nicht abgedeckt / offen

- Durchgängige „ohne Token → 403"-Contract-Tests je Routen-Gruppe (Slice 1).
- Response-Feld-Verträge zentral (Slice 2) statt vollständiger JSON-Snapshots.
