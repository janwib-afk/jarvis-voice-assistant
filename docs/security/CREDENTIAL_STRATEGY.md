# Jarvis – Credential Strategy (Phase 2)

> Ziel-Strategie für Secrets. **Anforderungsdokument** — es wird **keine** Secret-Migration
> in diesem Prompt ausgeführt. Stand 2026-07-14. Bezug: Threat **TM-007**,
> [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) SI-5.

## 1. Aktueller, belegter Zustand

- Zwei Pflicht-Secrets: `anthropic_api_key`, `elevenlabs_api_key` — **Klartext** in
  `config.json` (`config_loader.py:16` `REQUIRED_KEYS`). Werte hier `[REDACTED]`.
- `config.json` ist gitignored; die Settings-API lehnt Lesen/Schreiben der Keys ab
  (`config_loader.py:35` `PROTECTED_KEYS`); Fehlermeldungen nennen nur Schlüsselnamen.
- Werte werden **nie** geloggt; Validierung gibt nie Werte aus (`config_loader.py:66`).
- **Session-Token** ist kein gespeichertes Secret: pro Prozess erzeugt
  (`secrets.token_urlsafe(24)`, `server.py:44`), nie persistiert.
- Restrisiko heute: jeder lokale Prozess/Sync/Backup mit Lesezugriff auf `config.json`
  erhält die Klartext-Keys (TM-007).

## 2. Zielzustand: Windows Credential Manager / DPAPI

- Die zwei API-Keys werden über **DPAPI** (`CryptProtectData`, user+machine-gebunden) bzw.
  den **Windows Credential Manager** verschlüsselt abgelegt; `config.json` enthält dann
  keine Klartext-Keys mehr, sondern höchstens einen Verweis.
- Zugriff nur durch den Jarvis-Prozess im Kontext des angemeldeten Nutzers.

## 3. Secret-Typen, Besitz, Zugriff

| Secret | Typ | Besitzer | Zugriff | Ablage heute | Ablage Ziel |
|---|---|---|---|---|---|
| `anthropic_api_key` | API-Key | Nutzer | Server-Prozess | `config.json` Klartext | DPAPI/Cred-Manager |
| `elevenlabs_api_key` | API-Key | Nutzer | Server-Prozess | `config.json` Klartext | DPAPI/Cred-Manager |
| Session-Token | ephemer | Server | Prozess-intern | RAM (nicht persistiert) | unverändert |
| Test-Dummy-Keys | synthetisch | Repo | Tests | `tests/fixtures/config.test.json` | unverändert |

## 4. Migration aus `config.json` (geplant, nicht ausgeführt)

1. Beim Start prüfen, ob Keys bereits in DPAPI/Cred-Manager liegen.
2. Falls nur in `config.json`: einmalig einlesen → verschlüsselt ablegen → Klartext-Keys
   aus `config.json` entfernen (atomar wie `save_settings`, `config_loader.py:352`).
3. Rückroll-fähig: bis zur bestätigten erfolgreichen Ablage bleibt `config.json` die
   Quelle; erst danach Klartext entfernen.

## 5. Rotation und Widerruf

- Rotation durch erneute Eingabe (Setup/UI) → Ersetzen des verschlüsselten Werts.
- Widerruf: Nutzer widerruft den Key beim Provider und trägt einen neuen ein; Jarvis
  hält keinen Cache über den Prozess hinaus.

## 6. Test- und Entwicklungssecrets

- Tests nutzen ausschließlich die **synthetische Fixture** mit Dummy-Keys
  (`tests/fixtures/config.test.json`, keine echten Formate/Pfade) — bereits secret-frei.
- Kein echtes Secret in Tests, CI oder Dokumenten (SI-5).

## 7. Backup/Restore

- DPAPI-Secrets sind user+machine-gebunden → ein Backup der Datei allein stellt sie **nicht**
  wieder her. Restore-Prozess: Keys nach Wiederherstellung neu eintragen (dokumentieren).
- `config.json`-Backups dürfen nach der Migration **keine** Klartext-Keys mehr enthalten.

## 8. Redaction und Fehlerverhalten

- Redaction: Werte nie in Logs/Meldungen/Dokumenten; nur Schlüsselname + Speicherort
  (SI-5, SI-9). Diese Regel gilt bereits.
- Fehlerverhalten: fehlender/ungültiger Key → klarer `ConfigError` beim Start
  (`config_loader.py:89`), kein stiller Fallback; keine Wertausgabe.

## 9. Rückrollstrategie

- Die Migration ist reversibel bis zum Löschen des Klartexts (Schritt 4.3); vorher kann
  jederzeit auf `config.json` zurückgefallen werden. Nach dem Löschen erfolgt Rückroll
  über erneute Key-Eingabe.

## 10. Threat-ID-Zuordnung

- **TM-007** (Klartext-Secrets) — primär.
- **TM-003** (Token/Config-Manipulation) — profitiert von geringerer Secret-Exposition.
- Zielphase: **Phase 11** (Distribution/Recovery) mit möglicher Vorziehung nach
  Nutzerpriorität.
