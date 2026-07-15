# ADR 0005 – Credential-Ablage über DPAPI / Windows Credential Manager

- **Status:** akzeptiert (Phase 2, 2026-07-14) — erstellt unter der ausdrücklichen
  Nutzer-Delegation. Zielentscheidung; **keine Migration in diesem Prompt ausgeführt**.
- **Betrifft:** [../security/CREDENTIAL_STRATEGY.md](../security/CREDENTIAL_STRATEGY.md),
  Threat TM-007, SI-5.

## Warum ADR (3 Kriterien)

1. **Teuer zurückzunehmen:** legt Speicherformat, Migrationspfad und Backup-/Restore-
   Semantik fest (DPAPI ist user+machine-gebunden — Restore-Verhalten ändert sich).
2. **Ohne Kontext überraschend:** „Warum nicht einfach in `config.json`?" — braucht
   Begründung für spätere Entwickler.
3. **Echter Trade-off:** Einfachheit/Portabilität (Klartext-`config.json`) vs. Schutz vor
   lokalem Lesen (DPAPI, aber maschinen­gebundenes Restore).

## Kontext

Die zwei API-Keys liegen heute im Klartext in `config.json` (`config_loader.py:16`);
jeder lokale Prozess/Sync/Backup mit Lesezugriff erhält sie (TM-007). Die Settings-API
schützt sie bereits vor UI-Zugriff (`PROTECTED_KEYS`), aber nicht at rest.

## Entscheidung

- Zielablage der API-Keys: **DPAPI** (`CryptProtectData`, user+machine) bzw. **Windows
  Credential Manager**; `config.json` enthält danach keinen Klartext-Key mehr.
- Migration ist reversibel bis zum Entfernen des Klartexts; Tests nutzen weiter nur die
  synthetische Dummy-Fixture; Werte werden nie geloggt/übertragen (SI-5).

## Alternativen

1. **Klartext in `config.json` belassen** — einfach, aber TM-007 bleibt offen. Verworfen.
2. **Eigene Verschlüsselung mit im Repo/Config abgelegtem Schlüssel** — Schlüssel läge
   neben dem Geheimnis (Scheinsicherheit). Verworfen.
3. **Externer Secret-Manager/Cloud-Vault** — Overkill für lokalen Einzelbetrieb, neue
   Cloud-Abhängigkeit. Verworfen.

## Konsequenzen

- Reduziert die Secret-Exposition gegen lokale Prozesse/Backups deutlich.
- Restore wird komplexer (DPAPI maschinen­gebunden → Keys nach Restore neu eintragen) —
  dokumentiert in CREDENTIAL_STRATEGY §7.

## Sicherheitsauswirkungen

Schließt TM-007 (Klartext at rest); dämpft TM-003 (weniger lohnendes Config-Ziel).

## Rücknahmekriterien

Neu bewerten bei plattformübergreifendem Bedarf (macOS/Linux → Keychain/Secret Service)
oder wenn DPAPI-Restore-Reibung den Nutzen überwiegt. Umsetzungs-Zielphase: Phase 11.
