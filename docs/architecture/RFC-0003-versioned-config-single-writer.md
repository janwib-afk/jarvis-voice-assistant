# RFC-0003: Versioned Configuration and Settings Single Writer

## 1. Status und Entscheidungsgrundlage

**Accepted for incremental implementation** (2026-07-16) — **implementiert am
2026-07-16** (Phase 4D, siehe
[PHASE4D_VERSIONED_CONFIGURATION_MIGRATION.md](PHASE4D_VERSIONED_CONFIGURATION_MIGRATION.md)).

**Implementierungsevidenz:** `configuration.py` (Runtime-eigene tiefe Seam:
`snapshot()`/`settings_view()`/`mutate(intent, expected_revision)`), neun semantische
Intents, `schema_version` v0→v1 (nur Marker) getrennt von der opaken, nicht
persistierten `revision`, per-Runtime-`asyncio.Lock` mit `os.replace` als
Linearization Point, kompensierbares Live-Apply, Post-Commit-Refresh/Broadcast,
`409`/`If-Match` auf `/settings` inkl. sichtbarer Frontend-Konfliktbehandlung, ein
verifiziertes bytegenaues Pre-Migration-Backup unter der zuvor eingecheckten Regel
`config.json.*`. Die Befunde **A–E sind belegt behoben**, **F** ist eingegrenzt.
Der zweite produktive Writer (`config_loader.save_settings`) und die A6-Globals
(`server.config`/`CONFIG_PATH`/`STARTUP_WARNINGS`/`PERSIST_LAUNCHER`) sind entfernt.
Suite **688** grün (vorher 589), `test_configuration` 5× flakefrei, Smoke ohne Skips,
Browser-/Visual-/Native-Gates grün. **Keine persönliche Config wurde migriert.**
Slice-Commits: `33da00b`, `bc20b74`, `a16f7ca`, `a82c0f2`, `f2b7f12`, `6563379`,
`5cf608e`.

Die akzeptierte Entscheidung (Variante A, D1–D12) ist inhaltlich unverändert.

Grundlage: gezielter Architekturreview für **Kandidat 05** (löst das **A6**-Residual
aus [RFC-0002](RFC-0002-composition-root.md) auf) mit unabhängig reproduzierten
Defekten (§4), Design-It-Twice (§10) und einer Grilling-Session, in der der Nutzer die
Entscheidungen **D1–D12** und die Domain-Abgrenzung einzeln bestätigt hat. Dieser Prompt
ändert **keinen Produktionscode** (§45). Die Umsetzung erfolgt in Prompt 11 in kleinen,
einzeln rückrollbaren Slices (§39).

Folgt gemäß Masterplan **nach** RFC-0001 (Action deep module, Phase 4B, gemergt `57ba24a`)
und RFC-0002 (Composition Root, Phase 4A). Widerspricht weder RFC-0001/RFC-0002 noch
ADR-0003 (Test-Config-Seam) oder ADR-0005 (DPAPI) — siehe §42.

## 2. Problemzusammenfassung

Die persistierte Configuration hat heute **einen physischen Writer**
(`config_loader.save_settings` → atomarer `os.replace`), aber **drei logische
Schreib-Eingänge** (Settings, Music, Launcher) verteilt über `server.py` und **fünf
Modul-Globals**. Es gibt keinen serialisierten Read→compute→write-Pfad, kein
Concurrency-Token und keine kompensierbare Datei-plus-Live-Apply-Einheit. Daraus folgen
fünf reproduzierte Defekte (Datenverlust, Lost-Update, Cross-Instance-Schreiben,
fehlender Rollback, veralteter kanonischer Zustand) und ein TOCTOU-Risiko. RFC-0003
macht die Configuration zu einem **transaktionalen, Runtime-eigenen deep module** mit
genau einem serialisierten Änderungsweg, semantischen Mutationen, Schema-Versionierung,
Konflikterkennung und definierter Rücknahme.

## 3. Belegtes Writer-/Reader-Inventar

### Schreibende Eingangspfade

| # | Pfad | geschriebene Felder | Validierung | Persistenz | Live-Apply | Broadcast | Besitzer | Idempotenz | veraltete Basis? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `POST /settings` | `UI_EDITABLE_KEYS` (inkl. voller `apps`/`launcher`) | `validate_settings_update` | `save_settings` | `apply_settings` | `health` | `server.py` + Globals | ganzer Merge | **ja** — UI sendet vollen `apps`-Snapshot der Ladezeit (settings.js:167-170) |
| 2 | `POST /music/selection` | `selected_music_file` | Dateiname + Existenz | `save_settings` | `apply_settings` | `music_changed` | `server.py` | ja | TOCTOU-Fenster (§4-F) |
| 3 | `persist_launcher_block` | `launcher` + **voller `apps`-Snapshot aus `server.config`** | `validate_launcher_value` | `save_settings` | `apply_settings` | `launcher_changed` | `server.py` | bool statt Flip | **ja** — `apps` aus In-Memory-Global |
| 4 | 7 Launcher-/Profil-Routen | voller `launcher`-Block (`launcher_with_*`) | im Kern | via Kern | via Kern | `launcher_changed` | `app_launcher`-Globals | toggle/placement idempotent | **ja** — Block aus Modulstand |
| 5 | 4 Voice-Actions (`ctx.persist_launcher`) | voller `launcher`-Block | im Kern | via Kern | via Kern | `launcher_changed` | `ctx.persist_launcher` → `persist_launcher_block` | — | **ja** |
| 6 | weitere `save_settings`-Aufrufer | — | — | — | — | — | — | — | keine über die o.g. hinaus (rg-geprüft) |

### Lesende Eingangspfade

| Leser | gelesene Felder | Quelle |
|---|---|---|
| `Runtime.config` | ganze Config | Snapshot beim `aopen` (**veraltet nach Live-Apply**, §4-A) |
| `server.config` / `_public_settings` | `UI_EDITABLE_KEYS` | Modul-Global (faktische Wahrheit) |
| `assistant_core` | Persona/City/TTS + `build_system_prompt` | via `configure` |
| `memory` | `obsidian_inbox_path`/`_folder` | via `configure` |
| `app_launcher` | `apps`/`launcher` | via `configure` (`APPS`/`PROFILES`/`ACTIVE_PROFILE`) |
| `health.build_report` | Report-Felder | `server.config` + `STARTUP_WARNINGS` |
| Settings-Frontend | `UI_EDITABLE_KEYS` | `GET /settings` |
| Musik-Frontend | `music_folder`/`selected_music_file` | `GET /music/files` |
| Launcher-Frontend | `apps`/`launcher` | `GET /launcher/*` |
| `launch-session.ps1` | `launcher`/`active_profile`/`apps`/`music_folder`/`selected_music_file`/`music_volume`/obsidian | **direkt aus der Datei** |
| `clap-trigger.py` | `workspace_path` | **direkt aus der Datei** |
| Test-Fixtures | ganze Config | `tests/fixtures/config.test.json` (enthält unbekanntes `_comment`) |
| Baseline-/Browser-Harness | ganze Config | eigene Temp-Config |
| manuelle Bearbeitung | ganze Config | `config.json` von Hand |

**Begriffliche Trennung** (bewusst): *ein physischer Datei-Writer* vs. *drei logische
Writer*; *atomarer Dateiaustausch* (`os.replace`) vs. *echte Transaktionsatomizität*
(Datei + Live-Apply); *Schema-Version* (Formatmarker) vs. *Revision* (Concurrency-Token)
vs. *Config-Revision* vs. *Live-State* vs. *abgeleitete Modulzustände*.

## 4. Nachgewiesene Defekte und getrennte Architektur-Risiken

Alle Proben liefen ausschließlich gegen synthetische Temp-Configs (keine echte
`config.json`, keine persönlichen Pfade, keine Provider) und wurden danach entfernt.

| ID | Beobachtung | Probe (verifiziert) | Klasse |
|---|---|---|---|
| **A** | `Runtime.config` veraltet nach Live-Apply | `POST /settings city→Bremen` → `Runtime.config.city=Hamburg`, aber `server.config`/`GET /settings=Bremen` | **Defekt (Konsistenz)** — der als kanonisch deklarierte Zustand ist der veraltete |
| **B** | Cross-Instance-Schreiben über globalen `CONFIG_PATH` | zwei Runtimes/zwei Temp-Configs; `POST /settings` an App A schrieb **in Datei B** (`CONFIG_PATH` = zuletzt geöffneter Lifespan) | **Defekt (Isolation)** |
| **C** | Manuelle App durch veralteten `apps`-Snapshot verloren | manuell `vscode` + `manual_marker` in Datei, dann `POST /launcher/apps/obsidian/toggle` → `vscode` weg, `manual_marker` erhalten | **Defekt (Datenverlust)** — isoliert den `apps`-Snapshot als Ursache |
| **D** | Fehler nach erfolgreichem Dateischreiben, kein Rollback | Live-Apply (`assistant_core.configure`) wirft nach `save_settings` → Datei committed (Bremen), Exception, kein Restore | **Defekt (kein Rollback)** |
| **E** | Lost-Update aus zwei veralteten Launcher-Snapshots | zwei Änderungen aus gleicher Basis → erste (`obsidian=False`) vom veralteten Voll-Block überschrieben | **Defekt (Lost Update)** |
| **F** | Musik-Auswahl TOCTOU | Datei verschwindet zwischen Existenzcheck und Persistenz → Auswahl auf fehlende Datei persistiert (200) | **Architektur-Risiko/Fenster** (kein Crash; geringe Wahrscheinlichkeit im Einzelnutzer-Betrieb) |

A–E sind **nachgewiesene Defekte**, F ist ein **belegtes Fenster/Risiko**. Alle fünf
Defekte haben dieselbe Wurzel: kein serialisierter Single-Writer und veraltete
Voll-Snapshots als Änderungsträger.

## 5. Domainbegriffe

Vom Nutzer bestätigte Abgrenzung (kommt nach `CONTEXT.md`, ohne Architekturbegriffe):

- **Configuration** — das vollständige persistierte Dokument (`config.json`) **inklusive
  Secrets und unbekannter Felder**.
- **Settings** — die **UI-editierbare Projektion** daraus (Whitelist `UI_EDITABLE_KEYS`,
  ohne Secrets). Bestehende Definition bleibt, wird nur gegen *Configuration* abgegrenzt.

Architektur-/Implementierungsbegriffe (**nur** in diesem RFC, **nicht** in `CONTEXT.md`):
`ConfigStore`, `ConfigSnapshot`, Mutation/Intent, Revision, Lock, CAS, Backup,
`schema_version`, Adapterklassen, Implementierungsnamen.

## 6. Aktueller Zustand

- **Loader:** `config_loader.load_config` (fails-closed), `resolve_config_path`
  (`JARVIS_CONFIG_PATH`-Override), `save_settings` (fresh read → merge nur
  `UI_EDITABLE_KEYS` → atomarer `os.replace`). Kein `schema_version`.
- **Runtime:** lädt Config in `aopen`, spiegelt in Modul-Globals; `Runtime.config`
  wird nach Live-Apply nicht nachgeführt (A6-Residual, §4-A).
- **Server:** `apply_settings` mutiert `server.config`/`STARTUP_WARNINGS` und ruft die
  vier `configure()` auf; `persist_launcher_block` schreibt `launcher` + Voll-`apps`.
- **Frontend:** `settings.js` schickt vollen `apps`-Snapshot der Ladezeit; kein
  Konflikt-/Reload-Pfad. `main.js` verarbeitet `launcher_changed`/`music_changed`.
- **Direkte Leser:** `launch-session.ps1`, `clap-trigger.py` lesen die Datei ohne Server.

## 7. Ziele

1. Genau **ein** serialisierter, autoritativer Änderungsweg für die Configuration.
2. **Runtime-eigener kanonischer Snapshot** als einzige In-Memory-Wahrheit (behebt A/B).
3. **Semantische Mutationen** statt veralteter Voll-Snapshots (behebt C/E).
4. **Schema-Versionierung** (v0→v1) mit sauberer Startup-Migration (D5/D8/D11).
5. **Konflikterkennung** via Revision + `409`/`If-Match` auf `/settings` (D6).
6. **Kompensierbare** Datei-plus-Live-Apply-Transaktion mit definiertem Rollback (D9, behebt D).
7. **Secret-sicheres** Pre-Migration-Backup, dessen Schutz vor Erzeugung feststeht (D10).
8. Den Seam schaffen, an dem der A6-Cleanup (Prompt 11) andockt.

## 8. Nicht-Ziele (vom Nutzer bestätigt, D12)

Produktionscode; echte Config-Migration; echtes Backup; DPAPI/Credential Manager
(ADR-0005 entschieden, hier **nicht** implementiert); Verschiebung der API-Keys;
DB/SQLite/DB-Migrationen; allgemeines Backup-/Restore-System; Safe Mode;
Installer-/Update-Rollback; Event-Sourcing/Journal; Audit-Historie; File-Watcher;
allgemeiner Multi-Prozess-Koordinator; OS-weiter Lock als ungeprüftes Versprechen;
allgemeine REST-/WS-Protokollversionierung; `protocol_version`/`event_id`/`correlation_id`;
Conversation-/Job-State-Machines; Capability-/Policy-Kernel; Scheduler/Outbox/Saga;
strukturierte Logging-Gesamtmigration; UI-Redesign; Memory-Persistenzänderungen; Prompt 11.

## 9. Constraints

- Windows / CPython 3.10+ (SYSTEM_CHARTER); Standardtests kosten 0 Provider.
- **RFC-0002-Import-Sicherheit** bleibt: beim Import keine Config-I/O, keine Migration,
  kein Backup, keine Revisionsermittlung, kein Client.
- `core.autocrlf=true` ohne `.gitattributes` → kleine Slices; Text-Fixtures
  Universal-Newline lesen (Lehre aus Phase 4B).
- Atomarer Austausch der Hauptdatei (`os.replace`, same-volume) bleibt.
- `JARVIS_CONFIG_PATH` bleibt die explizite Test-/Start-Seam.
- Nur vertikale, einzeln rückrollbare Slices; kein Big-Bang.

## 10. Drei ernsthafte Varianten

**Variante A — Transaktionales Configuration-Modul** (empfohlen). Runtime-eigene tiefe
Seam: kleines Interface `snapshot()` + `mutate(intent, expected_revision)`; verborgen
read/migrate/validate/atomar-replace/live-apply/rollback; unveränderlicher Snapshot;
genau ein serialisierter Änderungsweg (`asyncio.Lock`); semantische Mutationen;
Konflikterkennung; definierte Rücknahme.

**Variante B — Writer-Queue/Actor.** Runtime-eigene `asyncio.Queue` + genau ein
Writer-Task; geordnete Commands; Backpressure; Cancel-/Shutdown-Semantik;
Writer-Task-Fehlerbehandlung. Löst Serialisierung, bringt aber Task-Lifecycle-Zeremonie
ohne Zusatznutzen (In-Process leistet ein Lock dasselbe).

**Variante C — Journal/Projection.** Append-only Änderungsjournal, `config.json` als
materialisierte Projektion; Sequenznummern; Replay/Rollback. Dual-Write-Komplexität,
**Klartext-Keys im Journal** (schlechtere Secret-Exposition), Überschneidung mit Phase 11
(Audit/Event-Sourcing) → zu früh.

Vergleich (Interface, verborgene Impl., Source of Truth, Linearization Point,
Concurrency, Manual-Edit, Migration, Rollback, Fehler nach Replace, Testoberfläche,
Lifecycle, Security, Kompatibilität, Rückrollbarkeit): siehe HTML-Report §7.

## 11. Entscheidung und Begründung (D1)

**Gewählt: Variante A.** Übernimmt von B semantische Commands und explizite
Serialisierung, **ohne** Hintergrund-Actor; C ist verfrüht und verschärft die
Secret-Exposition. Begründung nach **depth** (winziges Interface verbirgt
read/migrate/validate/replace/apply/rollback), **locality** (ein Ort besitzt jeden
Schreibvorgang — A/B/C/D/E haben genau einen Fix-Ort), **leverage** (Settings/Music/
Launcher teilen einen Mutations- und Konfliktpfad) und **seam placement** (am Runtime,
über echte Temp-Datei testbar — Dateisystem ist local-substitutable, keine abstrakte
Repository-Seam nur für Tests). „Ein Adapter = hypothetisch": ein Worker-Task wäre reine
Zeremonie.

## 12. Zielarchitektur

Eine **Configuration** ist ein deep module, besessen von `Runtime`: kleines Interface
(`snapshot` + `mutate`), große verborgene Implementation (Laden, Migration, Validierung,
atomarer Austausch, Live-Apply, Rollback, Revision). Der **kanonische In-Memory-Snapshot**
ist die einzige Wahrheit; `server.config`/`CONFIG_PATH`/`STARTUP_WARNINGS` sind temporäre
Migrationsadapter (Cleanup Slice 5). Die **Orchestrierung** (REST-/WS-Handler,
TTS/Refresh/Broadcast) bleibt außen und liest den Snapshot.

## 13. Öffentliches Interface der tiefen Configuration-Seam (konzeptionell)

Finale Signaturen bleiben der Implementierung überlassen; konzeptionell:

- `snapshot() -> ConfigSnapshot` — unveränderliche Sicht mit `schema_version`, einer
  opaken `revision` und dem vollständigen Dokument (inkl. Secrets, unbekannte Felder).
- `mutate(intent, expected_revision=None) -> MutationResult` — wendet **eine** semantische
  Änderungsabsicht gegen den neuesten kanonischen Zustand an; serialisiert; liefert neuen
  Snapshot oder einen **Konflikt** (bei überholter `expected_revision`).
- **Semantische Intents** (Kandidatenmenge, in Slice 0/2/4 zu fixieren): `SetSettings(dict)`,
  `SelectMusic(file)`, `SetAutostart(app_id, bool)`, `SetPlacement(app_id, monitor, zone)`,
  `ActivateProfile(id)`, `CreateProfile/RenameProfile/DeleteProfile/DuplicateProfile`.
- **Read-Projektion:** `settings_view()` liefert die UI-editierbare Projektion (ohne Secrets)
  plus die aktuelle `revision`.

Die **Testoberfläche ist genau dieses Interface** über eine echte Temp-Datei — nicht die
Modul-Globals, keine privaten Lock-/Temp-Helfer.

## 14. Verborgene Implementation

Hinter dem Interface: Fresh-Read der Datei, Versionsbestimmung, schrittweise Migration,
Vollvalidierung, `.tmp`-Schreiben + atomarer `os.replace`, deterministisches notwendiges
Live-Apply, Revisionsfortschreibung, Kompensation/Restore, der per-Runtime-Lock. Nicht am
Interface sichtbar: Lock-Mechanik, Temp-Datei-Handling, wie `revision` gebildet wird, wie
Intents auf Felder abbilden.

## 15. Besitz und Source of Truth (D2)

`Runtime` besitzt die Configuration-Seam und den kanonischen Snapshot — die **einzige**
In-Memory-Wahrheit. `server.config`, `server.CONFIG_PATH`, `server.STARTUP_WARNINGS` und
das globale Launcher-Persistenz-Residual sind **temporäre Adapter** und werden in Slice 5
entfernt, sobald alle Leser über die Seam laufen.

## 16. Dependency-Richtung

Die Configuration-Seam hängt nach außen an `config_loader` (Datei-I/O, Validierung) und —
für Live-Apply — an `assistant_core`/`memory`/`app_launcher` (stabile Module, direkte
Abhängigkeit, kein hypothetischer Port). Die REST-/WS-Handler und Voice-Actions hängen an
der Seam, nicht umgekehrt. Kein Zyklus (`config_loader` importiert die Capability-Module
nicht).

## 17. Lifecycle

Keine neuen Lebenszyklen, **kein** Hintergrund-Task. Die Seam entsteht in `Runtime.aopen`
(nach Migration, vor Wiring), lebt so lange wie die Runtime und wird in `aclose` nicht
gesondert behandelt (kein Task zu canceln). Der Lock ist ein per-Runtime-`asyncio.Lock`.

## 18. Import-Sicherheitsregeln

Beim `import` (RFC-0002): **keine** Config-I/O, **keine** Migration, **kein** Backup,
**keine** Revisionsermittlung, **kein** Client. `server.app` bleibt import-sicher mit
ungeöffneter Runtime. Laden/Migration/Backup entstehen ausschließlich in `Runtime.aopen`
bzw. im expliziten `python server.py`-Startcheck.

## 19. Schema-Versionierungsmodell (D5)

Top-Level `schema_version` als **Integer**. **Fehlend = Legacy v0.** Erste Zielversion =
**v1**. **v0→v1 ergänzt nur den Versionsmarker** — Reihenfolge, unbekannte Felder, Secrets,
Legacy-App-Strings und Mischform bleiben erhalten. Strengere Schemaänderungen erfordern
eine spätere eigene Version und eigene Migration. Die erste Migration darf die Config
**nicht** unter dem Vorwand der Versionierung normalisieren oder verschärfen.

## 20. Trennung von Schema-Version und Revision (D5)

- `schema_version` — **persistierte Formatversion** (Migration).
- `revision` — **opakes Concurrency-Token** eines geladenen Snapshots (Konflikterkennung),
  **kein** Schemafeld. Empfehlung (Slice 2): aus dem Snapshot **abgeleitet** (stabiler
  Hash), nicht zwingend persistiert. Die beiden dürfen nie vermischt werden.

## 21. Mutation-/Transaktionsablauf (D3)

1. Lock erwerben (per-Runtime).
2. **Fresh-Read** der Datei; Version bestimmen; ggf. in-memory nach aktueller Version bringen.
3. Falls `expected_revision` gesetzt und ≠ aktueller Revision → **Konflikt** (kein Schreiben).
4. Semantischen **Intent** gegen den frischen kanonischen Zustand anwenden.
5. Vollständigen Kandidaten **validieren** (`config_loader`).
6. `.tmp` schreiben, **atomarer `os.replace`** (Linearization Point).
7. Deterministisches **notwendiges Live-Apply**; bei Fehler → **Kompensation** (Restore).
8. Snapshot + `revision` fortschreiben.
9. Lock freigeben. **Post-Commit:** Refresh/Broadcast (Fehler = Degraded, kein Rollback).

## 22. Linearization Point

Der **atomare `os.replace`** unter dem Lock ist der Linearization Point: davor ist nichts
committed (Kompensation trivial = `.tmp` verwerfen), danach gilt die Datei als geschrieben
und nur ein Live-Apply-Fehler löst einen definierten Restore aus (§30/§31).

## 23. Concurrency- und Konfliktsemantik (D4)

Expliziter **per-Runtime-Lock**, genau ein Linearization Point. **Kein** allgemeiner
Multi-Prozess-Editor (ein zweiter Jarvis-Prozess wird nicht koordiniert — dokumentiertes
Restrisiko §43). Externe/manuelle Änderung **vor** Transaktionsbeginn wird frisch gelesen
und, falls gültig, als **neue Basis** übernommen. Eine Änderung **im** kritischen Fenster,
soweit über `revision`/mtime zuverlässig erkennbar, führt zu einem **kontrollierten
Konflikt**. Parallele Runtimes (Tests) sind vollständig isoliert, da `CONFIG_PATH` nicht
mehr global ist (behebt B).

## 24. Manual-Edit-Vertrag (D7)

Manuelle Bearbeitung bleibt unterstützt. Der Writer liest die Datei zu Mutationsbeginn
frisch; eine **gültige** erkannte Änderung wird als neue Basis übernommen. Eine
**beschädigte** oder **unbekannt-zukünftige** Version wird **nicht überschrieben**
(fails-closed). **Kein** File-Watcher, **keine** automatische Live-Synchronisierung.

## 25. Validierungsstrategie

Wiederverwendung der bestehenden `config_loader`-Validierer (`validate_config`,
`validate_settings_update`, `validate_apps_value`, `validate_launcher_value`,
`validate_placement_value`, `validate_music_*`). Nach jedem Intent wird der **vollständige
Kandidat** validiert, bevor er geschrieben wird. Meldungen nennen nur Schlüsselnamen, nie
Werte (keine Secrets).

## 26. Startup-Migration (D8)

In `Runtime.aopen`, **vor** Provider-Erzeugung und Wiring: lesen → Version bestimmen →
schrittweise **rein** migrieren → vollen Kandidaten validieren → Backup-/Rollback­voraus­setzungen
erfüllen → atomar ersetzen → **erst danach** Clients und Module verdrahten. Bei
Migrationsfehler: fails-closed, alte Datei bleibt unberührt. Keine Migration beim Import.

## 27. Future-Version-Verhalten

Eine Config aus einer **unbekannten zukünftigen `schema_version`** startet **nicht still**:
fails-closed mit lesbarer, secret-freier Meldung; die Datei wird **nicht** herabgestuft und
**nicht** überschrieben.

## 28. Backup- und Restore-Semantik (D10)

**Nur ein** klar benanntes, **byte-genaues Pre-Migration-Backup** (kein Versionsarchiv).
Erzeugung ausschließlich vor der ersten migrierenden Änderung. Restore-Verifikation:
das Backup wird nach dem Schreiben gelesen und byte-/wertgleich zum Original geprüft.
Retention: nur das letzte Pre-Migration-Backup. Speicherort/Name werden in Slice 6 final
festgelegt; **vor** der ersten Erzeugung muss die sichere Ignore-Regel stehen (§29).

## 29. Secret-Sicherheitsregeln für Backups (D10)

Das Backup enthält Klartext-Secrets. Heute ignoriert `.gitignore` **nur exakt
`config.json`** — ein `config.json.bak`/`.tmp` wäre ungeschützt. Regel: **vor** der ersten
Backup-Erzeugung (Slice 6) muss eine Ignore-Regel (z.B. `config.json.*` / `config.*.bak`)
oder ein Speicherort außerhalb des Repos feststehen. Backup-**Pfad und -Inhalt erscheinen
nie** in REST, WS oder Logs. `.gitignore`-Änderung ist Teil von Prompt 11, **nicht** dieses
RFC.

## 30. Persist-/Apply-/Refresh-/Broadcast-Fehlermatrix (D9)

| Schritt | Zeitpunkt | Fehlerfolge |
|---|---|---|
| Fresh-Read | vor Replace | Abbruch, keine Änderung, lesbarer Fehler |
| Migration | vor Replace (Start) | fails-closed, Datei unberührt |
| Vollvalidierung | vor Replace | Abbruch, `.tmp` verworfen, kein Schreiben |
| Backup | vor Replace (nur Migration) | Abbruch, keine Migration |
| `.tmp`-Schreiben | vor Replace | Abbruch, `.tmp` entfernt |
| **`os.replace`** | **Linearization Point** | Abbruch, alte Datei intakt |
| **notwendiges Live-Apply** | **nach Replace** | **Restore**: alte Datei + alter kanonischer Zustand wiederherstellen |
| Refresh (Wetter/Vault) | Post-Commit | **kein Rollback** — Degraded/Warn-Zustand |
| Broadcast (WS) | Post-Commit | **kein Rollback** — tote Clients aufräumen wie bisher |
| Restore | Fehlerpfad | letzter Ausweg: lesbarer Fehler + Degraded, nie stiller Zustand |

## 31. Rollbackstrategie

Vor dem Linearization Point ist Rollback trivial (`.tmp` verwerfen). Nach dem Replace ist
die Änderung nur dann committed, wenn das **notwendige** Live-Apply gelingt; sonst
Restore von Datei **und** kanonischem Snapshot. Refresh/Broadcast sind Post-Commit und
rollen nie eine gültige Config zurück.

## 32. REST-Kompatibilität

Pfade und Response-Shapes bleiben. **Additiv** (D6): `GET /settings` liefert eine
`revision`; `POST /settings` akzeptiert sie als Precondition (`If-Match`-artig) und
antwortet bei überholter Basis mit **`409 Conflict`** + Reload-Hinweis. Das ist **keine**
allgemeine REST-Protokollversionierung. Launcher/Music nutzen semantische Intents (kein
Voll-Snapshot) und brauchen `If-Match` primär nicht — das RFC präzisiert das, erzwingt es
aber nicht.

## 33. WS-Kompatibilität

Frame-Arten unverändert (`health`, `response`, `action`, `error`, `stop`,
`launcher_changed`, `music_changed`, `app_event`). Keine neuen Pflichtfelder, kein
`protocol_version`. Ein zusätzlicher optionaler Konflikt-/Reload-Hinweis über bestehende
Kanäle bleibt additiv.

## 34. Config-Kompatibilitätsmatrix

| Fall | v0→v1-Verhalten |
|---|---|
| versionlose gültige Config | erhält `schema_version:1`; sonst byte-treu erhalten |
| Version 1 | unverändert geladen |
| unbekannte zukünftige Version | **fails-closed**, nicht überschrieben/herabgestuft (§27) |
| beschädigtes JSON | `ConfigError`, nicht überschrieben |
| fehlende Config | `ConfigError` (Setup-Hinweis) |
| Legacy-App-Strings | unverändert erhalten (kein Zwangs-Objekt) |
| gemischte String-/Objekt-Apps | unverändert erhalten |
| fehlender Launcher-Block | bleibt fehlend; Defaults wie bisher in `app_launcher` |
| unbekannte zusätzliche Felder | **byte-/wertgetreu erhalten** (belegt in §4-C: `manual_marker`) |
| geschützte Secrets | erhalten, nie über REST/WS, nie in Logs |
| abgebrochene Migration | Datei unberührt, fails-closed |
| fehlgeschlagenes Live-Apply | Restore (§30) |
| manuelle Änderung vor Transaktion | frisch gelesen, als neue Basis übernommen (§24) |
| Konflikt während Transaktion | `409`/kontrollierter Konflikt (§23) |

## 35. PowerShell-/Clap-Trigger-Kompatibilität (D11)

`launch-session.ps1` und `clap-trigger.py` lesen die Datei direkt und ignorieren das neue
`schema_version`-Feld — sie laufen **unverändert** weiter. v1 benennt nichts um und
verschiebt nichts. Diese Skripte werden in Prompt 11 **nicht** angefasst (Nicht-Ziel).

## 36. Testoberfläche (für Prompt 11, im RFC festgelegt)

- **Configuration-Seam:** echte Temp-Datei; keine abstrakte Repository-Seam nur für Tests;
  Dateisystem ist local-substitutable; Verhalten über das öffentliche Interface prüfen;
  **keine** Tests privater Lock-/Temp-Helfer.
- **REST-Seam:** `create_app(Runtime(...))` mit eigener Temp-Config pro Runtime; echter
  `TestClient` (lifespan-fahrend); **keine** globalen `server.CONFIG_PATH`-Patches.
- **Parallelität:** zwei App-Instanzen, zwei Config-Pfade; gleichzeitige disjunkte
  Änderungen; gleichzeitige kollidierende Änderungen; stale Settings-Snapshot;
  Launcher-Mutationen aus gleicher Ausgangslage.

## 37. Fault-Injection-Plan (für Prompt 11)

Fehler bei: Lesen · Migrieren · Vollvalidierung · Backup · Temp-Schreiben · **vor**
Replace · **nach** Replace · notwendigem Live-Apply · Refresh · Broadcast · Restore.
Jeder injizierte Fehler prüft Disk-/Snapshot-/Modul-Konsistenz und die definierte
Kompensation.

## 38. Parallelitätsprüfungen (für Prompt 11)

Zwei Runtimes/zwei Configs schreiben disjunkt → beide Dateien korrekt und isoliert
(Regressionstest für B). Zwei Launcher-Mutationen aus gleicher Basis → beide Effekte
erhalten oder kontrollierter Konflikt (Regression für E). Stale Settings-Snapshot → `409`
(Regression für C/D6).

## 39. Inkrementelle Umsetzungsslices für Prompt 11

Jeder Slice: erste rote Beobachtung · öffentliche Test-Seam · minimale Änderung ·
Invarianten · Exit-Kriterium · Rollbackpunkt · erlaubte Dateien · Stopbedingungen.

- **Slice 0 — Charakterisierung & Migrationsvertrag.** Öffentliche Configuration-Test-Seam
  bestätigen; versionlose/v1/Future/Fehler-Fixtures; erste rote Tests; reine v0→v1-Migration;
  **noch kein Live-Writer**. *Rollback:* Migrationsfunktion + Tests entfernen.
- **Slice 1 — Tiefes Configuration-Modul & Runtime-Besitz.** Unveränderlicher Snapshot;
  Runtime-eigener Besitzer; Load/Migrate/Validate; REST-/WS-Verträge unverändert; Import
  seiteneffektfrei. *Rollback:* Modul entfernen, `aopen` auf alten Load zurück.
- **Slice 2 — Settings-Writer & Konflikterkennung.** `GET/POST /settings`; Revision/`If-Match`
  gemäß D6; Frontend-Konfliktbehandlung; Secrets/unbekannte Felder erhalten. *Rollback:*
  `save_settings`-Pfad zurück, Revision-Feld entfernen.
- **Slice 3 — Musik-Mutation.** Auswahl + Ordnerprüfung in einem konsistenten Snapshot;
  Response + `music_changed` erhalten. *Rollback:* alte `music_selection` zurück.
- **Slice 4 — Launcher REST & Voice.** Semantische Launcher-Mutationen; **kein** veralteter
  Voll-Snapshot; bestehende Routen + Action-Ergebnisse + `launcher_changed` erhalten.
  *Rollback:* `persist_launcher_block` auf Voll-Snapshot zurück.
- **Slice 5 — A6-Cleanup.** `server.config`/`CONFIG_PATH`/`STARTUP_WARNINGS`, globales
  Launcher-Residual, global-patchende Tests entfernen — **nur** wenn alle Leser über die
  Seam laufen. *Rollback:* Adapter wieder einsetzen.
- **Slice 6 — Fault Injection, Parallelität, Rollback, Backup, Doku, Hosted CI.** Fehler vor/
  nach Replace; zwei App-Instanzen; parallele Änderungen; stale UI; manuelle Änderungen;
  Migration-Backup/Restore (**Ignore-Regel vor Backup**); Hosted Windows CI. *Rollback:*
  je Prüfung/Datei einzeln.

Prompt 10 implementiert **keinen** dieser Slices.

## 40. Rückrollpunkt je Slice

Jeder Slice ist ein eigener, revertierbarer Commit; vor jedem Slice ist der letzte grüne
Stand (Suite + Smoke) der Rückrollpunkt. Slice 5 (A6-Cleanup) ist erst zulässig, wenn alle
Leser migriert und alle Gates grün sind — davor bleiben die Adapter das Sicherheitsnetz.

## 41. Security- und Datenschutzinvarianten

Secrets nie über REST/WS; `PROTECTED_KEYS` unverändert; UI-Whitelist unverändert;
unbekannte Felder + Secrets byte-/wertgetreu erhalten; Meldungen nennen nie Werte;
Backup-Pfad/-Inhalt nie in REST/WS/Logs; keine echte persönliche Config in Tests; keine
Provider-/Desktopwirkung in Tests; nur lokale Bindung.

## 42. ADR-Beziehungen

**Kein neues ADR** (nicht ohne separate Nutzerbestätigung). Stützt **ADR-0003**
(Test-Config-Seam — `JARVIS_CONFIG_PATH` bleibt) und **RFC-0002** (schließt das
A6-Residual). **ADR-0005** (DPAPI) bleibt entschieden und wird hier **nicht** implementiert
(API-Keys bleiben, wo sie sind). Kein Konflikt mit **ADR-0001/0002/0004**, **RFC-0001**.

## 43. Risiken und akzeptierte Restrisiken

- **Multi-Prozess:** ein zweiter, gleichzeitig laufender Jarvis-Prozess wird **nicht**
  koordiniert (D4) — akzeptiertes Restrisiko; Einzelprozess ist der reale Betrieb.
- **TOCTOU-Fenster (§4-F):** die Musik-Existenzprüfung bleibt ein schmales Fenster;
  Minderung durch Mutation-im-Snapshot, aber Dateisystem-Races sind nie vollständig
  eliminierbar — akzeptiert (geringe Wahrscheinlichkeit, kein Datenverlust).
- **Revision-Falschklassifikation:** ein zu grobes Token könnte harmlose Änderungen als
  Konflikt melden — Minderung durch abgeleitetes, stabiles Token; in Slice 2 zu justieren.
- **Zeilenenden (autocrlf):** Fixtures/Goldens Universal-Newline lesen.

## 44. Implementierungs- und Freigabegates

- **Je Slice:** gezielter Test rot→grün; volle Suite grün; Smoke Exit 0, 0 unerwartete
  Skips; keine REST-/WS-/Prompt-Regression.
- **Vor Slice 5 (A6-Cleanup):** alle Leser über die Seam; Parallel-/Fault-Tests grün.
- **Vor Backup-Erzeugung (Slice 6):** sichere Ignore-Regel/Speicherort steht (D10).
- **Abschluss:** Hosted Windows CI (Fast + Browser) grün; `git diff --check` sauber.

## 45. Prompt 10 ändert keinen Produktionscode

Dieser Prompt liefert ausschließlich Architektur/Dokumentation: dieses RFC, die
`CONTEXT.md`-Domain-Abgrenzung (Configuration vs. Settings) und eine kurze Statusnotiz in
`CURRENT_STATE.md`. **Kein** Produktionscode, **keine** Tests, **kein** `schema_version` in
echten Dateien, **keine** Migration, **kein** Backup, **keine** REST-/WS-Routenänderung.
Der HTML-Report bleibt ausschließlich im Temp-Verzeichnis.
