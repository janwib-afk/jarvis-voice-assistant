# Phase 4D — Versionierte Configuration mit Single Writer (Umsetzung von RFC-0003)

> Stand 2026-07-16. Umsetzung von [RFC-0003](RFC-0003-versioned-config-single-writer.md)
> (`Accepted for incremental implementation`). Löst das **A6-Residual** aus
> [RFC-0002](RFC-0002-composition-root.md) endgültig auf. Basis: `origin/master`
> `f23d69d`.

## Ausgangszustand

Ein *physischer* Writer (`config_loader.save_settings` → atomarer `os.replace`), aber
**drei logische** (Settings, Music, Launcher) über `server.py` und fünf Modul-Globals.
Kein serialisiertes Read→compute→write-Fenster, kein Concurrency-Token, keine
kompensierbare Datei-plus-Live-Apply-Einheit. Fünf reproduzierte Defekte (A–E) plus ein
TOCTOU-Risiko (F) — siehe RFC-0003 §4.

## Umgesetzte Slices, Commits und Rückrollpunkte

| Slice | Commit | Inhalt | Rückrollpunkt |
|---|---|---|---|
| **0** | `33da00b` | Migrationsvertrag (v0/v1/Future/Corrupt), `.gitignore config.json.*`, v1-Marker in allen eingecheckten synthetischen Configs. Kein Live-Writer. | Commit reverten; nichts Produktives war aktiv |
| **1** | `bc20b74` | `configuration.Configuration` + Runtime-Besitz; Load/Migrate/Validate in `aopen` vor Provider/Wiring; bytegenaues Pre-Migration-Backup | Commit reverten → `Runtime.load_config` auf `config_loader.load_config` |
| **2** | `a16f7ca` | `mutate()`-Kern + `SetSettings` + Revision + `409`/`If-Match` + Frontend-Konfliktbehandlung + Browser-Flow | Commit reverten → alter `save_settings`-Pfad |
| **3** | `a82c0f2` | `SelectMusic`-Intent; Ordner-/Existenzprüfung im selben Snapshot | Commit reverten |
| **4** | `f2b7f12` | Launcher-Intents (7) für REST **und** Voice; `ActionContext.mutate_launcher` | Commit reverten → Voll-Snapshot-Persistenz |
| **5** | `6563379` | A6-Cleanup: `server.config`/`CONFIG_PATH`/`STARTUP_WARNINGS`/`apply_settings`/`PERSIST_LAUNCHER`/`save_settings` entfernt; `Runtime.config` = read-only Projektion | Commit reverten → Adapter zurück |
| **6** | `5cf608e` | Vollständige Fault-Matrix, Parallelitätsprüfungen, Backup-Vertrag | Commit reverten |

Jeder Slice ist ein eigener, grüner, einzeln revertierbarer Commit. Es gab keine
absichtlich roten Commits.

## Finale Configuration-Schnittstelle

```python
cfg = runtime.configuration                      # genau EINE Instanz je Runtime

cfg.snapshot()      -> ConfigSnapshot            # kanonisch, NUR-LESBAR
                    #   .document  (MappingProxy/Tuples; .as_dict() = tiefe Kopie)
                    #   .schema_version : int
                    #   .revision       : str    (opak, NICHT persistiert)
cfg.settings_view() -> {"settings": {...}, "revision": "..."}   # nie Secrets
await cfg.mutate(intent, expected_revision=None, apply=None) -> MutationResult
```

**Semantische Intents:** `SetSettings`, `SelectMusic`, `SetAutostart`, `SetPlacement`,
`ActivateProfile`, `CreateProfile`, `DuplicateProfile`, `RenameProfile`, `DeleteProfile`.
Alle rechnen gegen das **frisch gelesene Dokument der laufenden Transaktion** — nie gegen
Modul-Globals oder einen vorberechneten Voll-Block.

## Schema-Version und Revision (strikt getrennt)

| | `schema_version` | `revision` |
|---|---|---|
| Zweck | persistierte **Formatversion** (Migration) | **Concurrency-Token** (Konflikt) |
| Persistiert | ja (Top-Level-Integer) | **nein** (aus dem Inhalt abgeleitet) |
| Fehlend | = v0 (Legacy) | — |
| Ziel | **v1** | opak, ändert sich bei jeder Inhaltsänderung |

**v0→v1 ergänzt ausschließlich den Marker.** Reihenfolge, unbekannte Felder, Secrets,
Legacy-App-Strings, Mischformen und ein fehlender Launcher-Block bleiben unverändert.
Unbekannte **Zukunftsversionen** und beschädigtes JSON sind **fails-closed** und werden
nie überschrieben.

## Mutationsablauf und Linearization Point

Lock → Fresh-Read → Version/Migration → Revisionsprüfung → Intent anwenden →
Vollvalidierung → `.tmp` schreiben → **`os.replace`** (Linearization Point) →
notwendiges Live-Apply → publish → Lock frei. **Post-Commit** (kein Rollback):
Refresh + Broadcast.

## Backup-/Rollback-Vertrag

- **Ein** Pre-Migration-Backup `config.json.pre-v1.bak`, **bytegenau**, nach dem
  Schreiben **rückgelesen und verifiziert**; nur das letzte bleibt. Nur bei tatsächlicher
  Migration (v1-Datei erzeugt keines).
- Backup- und Temp-Suffix sind Suffixe von `config.json` → die **vor** dem ersten Backup
  eingecheckte Regel `config.json.*` deckt sie ab (per `git check-ignore` verifiziert,
  Gegenprobe: `config.example.json`/Fixture bleiben sichtbar).
- Backup-Pfad/-Inhalt erscheinen nie in REST, WS oder Logs (per Test belegt).
- **Rollback:** vor dem Replace trivial (`.tmp` verwerfen); nach dem Replace stellt ein
  fehlgeschlagenes notwendiges Live-Apply Datei **und** Snapshot wieder her.

## Fault-Injection-Matrix (alle grün)

| Fehler | Zeitpunkt | Beobachtetes Verhalten |
|---|---|---|
| Lesefehler | vor Replace | Abbruch; Datei/Snapshot/Revision unverändert |
| Migrationsfehler (Future) | vor Replace | fails-closed; Datei bytegleich |
| Vollvalidierungsfehler | vor Replace | Abbruch; nichts geschrieben |
| Backup-Erzeugungsfehler | vor Migration | Migration bricht ab; Datei unberührt |
| Backup-Verifikation | vor Migration | ungleiches Backup ⇒ Abbruch |
| Temp-Schreibfehler | vor Replace | Abbruch; nichts geschrieben |
| Erkannter Konflikt | vor Replace | `ConfigConflict`; kein Schreiben, kein Live-Apply |
| `os.replace`-Fehler | Linearization Point | Abbruch; alte Datei intakt |
| Live-Apply-Fehler | **nach** Replace | **Restore** von Datei **und** Snapshot |
| Refresh-Fehler | Post-Commit | **kein** Rollback; Degraded-Meldung |
| Broadcast-Fehler | Post-Commit | **kein** Rollback; Warnung im Log |
| Restore-Fehler | Fehlerpfad | propagiert — kein stiller Teilerfolg |

Secrets erscheinen in **keiner** Meldung (per Test belegt).

## Parallelitätsprüfungen

Fünf disjunkte Mutationen gleichzeitig → alle überleben. Zwei kollidierende Revisionen →
genau **ein** Gewinner, genau **ein** kontrollierter Konflikt (kein Lost-Update).
Wiederholte Launcher-Mutationen idempotent. Zwei Configurations auf zwei Pfaden
vollständig isoliert. **Keine Multi-Prozess-Garantie behauptet** (D4).

## Behobene Defekte

| ID | Vorher | Nachher (belegt) |
|---|---|---|
| **A** | `Runtime.config` veraltet nach Live-Apply | `Runtime.config` ist read-only Projektion des Snapshots — Runtime == Snapshot == `GET /settings` |
| **B** | `POST` an App A schrieb in Datei B (globaler `CONFIG_PATH`) | zwei Runtimes/zwei Pfade nachweislich isoliert |
| **C** | manuelle App durch veralteten `apps`-Voll-Snapshot verloren | Intents + Pinning gegen die frische Basis — manuelle App und unbekannte Felder überleben |
| **D** | Datei committed, Live-Apply-Fehler ohne Rollback | Restore von Datei **und** Snapshot |
| **E** | Lost-Update aus zwei veralteten Launcher-Snapshots | beide Wirkungen erhalten bzw. kontrollierter Konflikt |
| **F** | Musik-TOCTOU | **eingegrenzt, nicht beseitigt** — die Prüfung läuft jetzt gegen die frische Transaktionsbasis; ein schmales Dateisystem-Fenster bleibt (siehe Restrisiken) |

## Erhaltene Verträge

REST-Pfade und Response-Formen (`revision` ist **additiv**; `409` nur bei vorhandenem,
überholtem `If-Match`; ohne Header bleibt es erlaubt) · WS-Frames (`health`,
`launcher_changed`, `music_changed`, …) unverändert · `PROTECTED_KEYS`/UI-Whitelist ·
Secrets nie über REST/WS · Config-/Memory-Dateiformate · Legacy-App-Strings und
Mischform · fehlender Launcher-Block · `JARVIS_CONFIG_PATH` · Import-Sicherheit
(RFC-0002) · Entry Points (`server.app`, `uvicorn server:app`, `python server.py`,
Launcher) · Action-Antworttexte und **byte-genaue Prompt-Goldens** · APP_OPEN-Allowlist ·
`launch-session.ps1` und `clap-trigger.py` **unverändert**.

## Testevidenz (lokal, frisch)

| Prüfung | Ergebnis |
|---|---|
| `tests/test_configuration.py` (neu) | grün, **5× flakefrei** |
| Volle Suite | **688 Tests, OK** (Baseline vorher 589) |
| Smoke | grün, **0 unerwartete Skips** |
| Browser-Flows (inkl. neuem kritischen `settings_conflict`) · A11y · Reduced Motion | grün |
| **Visual-Regression** (ohne `--update`) | grün |
| Native · `verify_phase4` · `verify_phase5` | grün |

## Keine persönliche Config migriert

**Die persönliche `config.json` wurde zu keinem Zeitpunkt geöffnet, migriert oder
gesichert.** Alle Tests und Proben liefen ausschließlich gegen temporäre Dateien; nach
jedem Slice wurde verifiziert, dass sie weiterhin **v0** ist und **kein** `config.json.*`
daneben liegt. Sie wird erst beim nächsten echten Jarvis-Start migriert — dann mit
bytegenauem, verifiziertem Backup.

## Während der Umsetzung gefundene Fehler (eigene)

- **`_post_commit` rief `broadcast_health(rt)`, während der Parameter `runtime` hieß**
  (`NameError`). Der Health-Broadcast schlug **still** fehl und wurde nur als Degraded
  geloggt — genau die Klasse Fehler, die ein Post-Commit-Pfad verdeckt. Behoben in
  Slice 5, Regression: `SettingsBroadcastTests`.
- Vier durch ein Heredoc verstümmelte Backslashes in Testdaten (SyntaxWarnings).

## Bekannte Restrisiken

- **Multi-Prozess:** ein zweiter, gleichzeitig laufender Jarvis-Prozess wird nicht
  koordiniert (D4, akzeptiert).
- **Musik-TOCTOU (F):** eingegrenzt, nicht eliminierbar — eine vollständige
  Dateisystem-Transaktion ist nicht möglich und wird nicht versprochen.
- **Serielle Isolation:** Persona/City, `APPS/PROFILES`, `VAULT_PATH` und der
  Browser-Singleton leben weiter als Modul-Globals (K03/K04, D4-Residual) — der
  Configuration-Besitz ist davon unberührt.
- **`Runtime.config`** bleibt als read-only Kompatibilitätsprojektion bestehen (begründet
  in RFC-0003 Slice 5); sie kann nicht veralten und nicht zurückschreiben.

## Nicht umgesetzt (unverändert Nicht-Ziele)

DPAPI/Credential Manager (ADR-0005 bleibt entschieden, nicht implementiert) ·
Verschiebung der API-Keys · DB/SQLite · allgemeines Backup-/Restore-System · Safe Mode ·
Event-Sourcing/Journal/Audit · File-Watcher · Multi-Prozess-Koordinator · allgemeine
REST-/WS-Protokollversionierung · `protocol_version`/`event_id`/`correlation_id` ·
State Machines · Capability-/Policy-Kernel · Scheduler/Outbox/Saga · strukturierte
Logging-Gesamtmigration · UI-Redesign · Memory-Persistenzänderungen · Prompt 12.
