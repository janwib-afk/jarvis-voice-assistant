# RFC-0004: Structured Operational Logging and Redaction

## 1. Status und Datum

**Accepted for incremental implementation** (2026-07-17).

**Entscheidungsgrundlage.** Der Nutzer hat **D1–D6, D8 und D9** in einer Grilling-Session
einzeln bestätigt. Für **D7 und D10–D12** sowie für die Annahme dieses RFC hat er
ausdrücklich delegiert („Wähle IMMER deine Empfehlung aus, bis der Prompt abgeschlossen
ist") — dieselbe Delegationsform, auf der bereits [RFC-0001](RFC-0001-action-deep-module.md)
seine Variantenwahl stützt. Die Annahme beruht damit auf einer ausdrücklichen Delegation,
**nicht** auf einer Einzelprüfung jeder Option; das ist hier bewusst transparent vermerkt.

Prompt 12 ändert **keinen Produktionscode, keine Tests, keine Workflows und keine
Dependencies** (§26). Die Umsetzung folgt in Prompt 13 in kleinen, rückrollbaren Slices.

Folgt auf RFC-0001 (Action deep module), [RFC-0002](RFC-0002-composition-root.md)
(Composition Root) und [RFC-0003](RFC-0003-versioned-config-single-writer.md)
(Versioned Configuration, gemergt `e6fed2e`). Widerspricht keinem bestehenden ADR.

## 2. Ausgangslage und Evidenz

Alle Befunde stammen aus einer Bestandsaufnahme am Code (`origin/master` `e6fed2e`) und
aus einer Leckprobe mit **ausschließlich synthetischen Sentinel-Werten**, temporären
Dateien und lokalen Test-Doubles. Keine echten Provider, keine echten Apps, keine
persönlichen Daten; die Probe wurde danach entfernt. Der reale `jarvis-launcher.log`
wurde **nicht gelesen** (nur seine Größe geprüft).

### Produzenten (10 Logger, 78 Aufrufe)

| Logger | Modul | Aufrufe | davon DEBUG |
|---|---|---|---|
| `jarvis` | `server.py` | 19 | 1 |
| `jarvis.core` | `assistant_core.py` | 19 | 5 |
| `jarvis.apps` | `app_launcher.py` | 13 | 0 |
| `jarvis.browser` | `browser_tools.py` | 9 | 1 |
| `jarvis.memory` | `memory.py` | 9 | 0 |
| `jarvis.tts` | `tts.py` | 3 | 1 |
| `jarvis.clipboard` | `clipboard_tools.py` | 2 | 0 |
| `jarvis.configuration` | `configuration.py` | 2 | 0 |
| `jarvis.actions` | `actions.py` | 1 | 0 |
| `jarvis.monitors` | `monitors.py` | 1 | 0 |

**Dritte:** `uvicorn`/`uvicorn.access` (Default-Config, Request-Zeilen), `httpx`
(Request-Zeilen auf INFO), `anthropic` (nutzt httpx), `playwright`.
`config_loader.py`, `health.py`, `runtime.py`, `screen_capture.py` loggen nicht.

### Sinks — ein `basicConfig`, vier reale Senken

| Sink | Wohin | Aufbewahrung |
|---|---|---|
| stderr | Konsole | flüchtig |
| **`jarvis-launcher.log`** | `jarvis-launcher.pyw` biegt `sys.stdout`/`sys.stderr` um; der **Server-Subprozess schreibt in denselben rohen Handle** | **~1 MB × 3 Backups, dauerhaft auf Platte** |
| **UI-Dialog** | `jarvis-launcher.read_log_tail(15)` zeigt Logzeilen im Fenster | flüchtig, aber sichtbar |
| `jarvis-launch.log` | `scripts/launch-session.ps1` (`Add-Content`) | wächst unbegrenzt |

Beide Logdateien sind gitignored (`*.log`, `*.log.*`) — belegt per `git check-ignore`.
Die einzige Formatierung ist heute
`%(asctime)s [%(levelname)s] %(name)s: %(message)s`; Level über `JARVIS_LOG_LEVEL`.

### Evidenztabelle (Auszug der Risikopfade)

| Produzent | Sink | aktueller Inhalt | Datenklasse | Risiko | gewünschte Behandlung |
|---|---|---|---|---|---|
| `browser_tools` (INFO) | Datei/UI | **volle URL inkl. Query** (Suchbegriff) | personal/sensitive | **hoch** | nur Schema+Host |
| `assistant_core` „Action-Ergebnis" (DEBUG) | Datei/UI | Clipboard-/Vault-/Screen-/Inbox-**Inhalt** | sensitive | **hoch** | nie roh; Länge/Typ/Action |
| `assistant_core` „Action payload" (DEBUG) | Datei/UI | Nutzer-/Aktionstext | personal | hoch | nie roh; Action-Typ + Länge |
| `server` „You:" (DEBUG) | Datei/UI | **rohe Nutzereingabe** | personal | hoch | nie roh; Länge |
| `assistant_core` „LLM raw"/„Jarvis:" (DEBUG) | Datei/UI | LLM-Antwort (gekürzt) | personal | hoch | nie roh; Länge |
| `browser_tools`/`app_launcher` (`exc_info=True`) | Datei/UI | **Exception-Message + Traceback** | bis sensitive | hoch | Typ + Ort; Message redigiert |
| `app_launcher`/`server` (INFO) | Datei/UI | App-/Profil-IDs, Placement, Musikdateiname | local | niedrig | erlaubt (Betriebsdiagnose) |
| `configuration` (INFO) | Datei/UI | „von Version 0 auf 1 migriert" | local | niedrig | erlaubt |
| `tts` (DEBUG) | Datei/UI | Statuscode + Bytegröße | local | niedrig | erlaubt |
| `uvicorn.access` | Datei/UI | Methode/Pfad/Status | local | niedrig | erlaubt (Filter als Netz) |
| `httpx` (INFO) | Datei/UI | Provider-URL (Key steckt im **Header**, nicht in der URL) | local | niedrig | Host statt voller URL |
| `config_loader` | — | loggt nicht; Meldungen nennen nie Werte | secret | — | unverändert |

### Belegte Leckvektoren (Sentinel-Probe)

| # | Vektor | Level | Ergebnis |
|---|---|---|---|
| **L1** | Suchbegriff in voller URL | **INFO (Default!)** | Sentinel im Sink |
| L2 | Clipboard-Inhalt via „Action-Ergebnis" | DEBUG | Sentinel im Sink |
| L3 | Vault-Inhalt via „Action-Ergebnis" | DEBUG | Sentinel im Sink |
| L4 | Rohe Nutzereingabe („You:") | DEBUG | Sentinel im Sink |
| L5 | Exception-**Message** mit Inhalt | WARNING | Sentinel im Sink |
| L6 | Traceback | WARNING | im Sink |

## 3. Problemdefinition

Das Logging ist **unstrukturierter Freitext ohne zentrale Redaction**. Jeder Aufrufer
entscheidet selbst, was in die Formatzeichenkette wandert; es gibt keine Feld-Allowlist,
keine Datenklassenbindung und keinen Schutz für Drittanbieterlogs. Daraus folgt:

- **L1 verletzt die bereits verbindliche Regel** der Datenklassen-Tabelle
  (`network-read` → „**log Zielhost**") — und zwar auf **INFO**, dem Standardlevel, mit
  dauerhafter Persistenz in einer rotierenden Datei.
- **L2–L4** persistieren rohe `sensitive`/`personal`-Inhalte, sobald jemand
  `JARVIS_LOG_LEVEL=DEBUG` setzt — die Datei überlebt Neustarts und der UI-Tail zeigt
  Ausschnitte an.
- **L5/L6** hängen an `exc_info=True`: eine Exception-Message kann Inhalt tragen.
- Es gibt **keinen Test-Seam**: kein Test prüft heute, was am Sink ankommt.

## 4. Ziele

1. **Strukturierte Betriebsereignisse** statt Freitext: benannte Events mit erlaubten Feldern.
2. **Zentrale, standardmäßig geschlossene Redaction** — unbekannte Felder erscheinen nie.
3. **Keine rohen privaten Inhalte auf irgendeinem Level** (D3).
4. **Sichere Exception-/Traceback-Behandlung** (D6).
5. **Schutznetz** unter Legacy- und Drittanbieterlogs (D1: Hybrid).
6. **Fail-closed**: Redaction kann nie offen fehlschlagen; Logging bricht nie den Ablauf ab (D8).
7. **Import-Sicherheit** wie RFC-0002; Konfiguration einmalig am Startpfad (D9).
8. **Öffentlicher Test-Seam** am formatierten Sink-Output (D12).
9. **Keine neue externe Abhängigkeit**; Launcher-Diagnose bleibt lesbar (D4).

## 5. Nicht-Ziele

`protocol_version`, `event_id`, `correlation_id`, neue Wire-`session_id`,
Wire-Sensitivity-Felder, neue REST-/WS-Schemas, State Machines, Conversation-/Voice-/
Job-Kernel, Capability-/Policy-Kernel, **Audit-Event-System**, Metriken, Distributed
Tracing, Remote-Telemetrie, Diagnostic Bundles, Safe Mode, Installer-Umbau, DPAPI-/
Credential-Umbau, UI-Redesign, Config-Schema-Änderungen, Produktionscode, Testcode,
Workflows, Dependencies. **Launcher/PowerShell** sind in diesem RFC dokumentiert, aber
nicht Umsetzungsscope (D2). REST-, WS-, Config-, Memory- und UI-Verträge bleiben unverändert.

## 6. Sicherheits- und Datenschutzanforderungen

- **SI-9 wird verschärft** (D3): statt „private Inhalte nur DEBUG" gilt künftig
  *„rohe private Inhalte erscheinen auf keinem Level"*. Die Anpassung von
  `SECURITY_REQUIREMENTS.md` gehört in den Umsetzungs-Slice, **nicht** in dieses RFC.
- `secret` (API-Keys, Session-Token): **nie**, in keiner Form, auf keinem Level.
- `sensitive` (Screen/Clipboard/Vault/Memory-Inhalt): **nie roh**; nur Metadaten.
- `personal` (Gespräch, Inbox, Namen in Freitext): **nie roh**; nur Metadaten.
- `network-read`: **nur Zielhost** (Schema+Host), nie Query/Pfad (D7).
- `local` (App-/Profil-IDs, Action-Typen, Zähler, Statuscodes): erlaubt.
- Backup-Pfade/-Inhalte (RFC-0003 §29): **nie** in Logs.
- Meldungen nennen weiterhin nie Config-Werte (`config_loader`-Regel bleibt).

## 7. Begriffe und Datenklassen

- **Operational Log Event** — eine benannte, strukturierte technische Betriebsdiagnose
  (Gegenstand dieses RFC).
- **Audit Event** — nachvollziehbare Sicherheits-/Benutzeraktion. **Späterer Scope.**
- **Telemetrie/Metriken/Tracing** — späterer Observability-Scope.
- **Redaction** — die zentrale, allowlist-basierte Umwandlung eines Feldwerts in eine
  sichere Repräsentation (oder dessen Weglassen).
- **Sink** — die Stelle, an der der endgültig formatierte Output entsteht.

Datenklassen unverändert übernommen: `public` · `local` · `personal` · `sensitive` ·
`secret` (SECURITY_REQUIREMENTS, CAPABILITY_MATRIX).

## 8. Untersuchte Varianten

| Kriterium | **A** Zentraler Filter/Formatter | **B** Semantisches Event-Modul | **C** Hybrid (gewählt) |
|---|---|---|---|
| Modultiefe/Interface | keins (Filter am Sink) | klein, semantisch | klein + Schutzfilter |
| Sicherheitsgarantie | Mustererkennung — **rät** | **strukturell** (Allowlist) | strukturell **+** Netz |
| Fail-closed | schwer | ja | ja |
| Testbarkeit | Filter isoliert | Sink-Output | Sink-Output |
| Import-Sicherheit | Filter muss früh hängen | einfach | einfach |
| Runtime-/Root-Ownership | unklar | Startpfad | Startpfad |
| Launcher/CI-Kompatibilität | hoch | hoch | hoch |
| **Drittanbieterlogs** | **abgedeckt** | **nicht** abgedeckt | **abgedeckt** |
| Migrationsaufwand | klein | groß (78 Aufrufe) | inkrementell |
| Rückrollbarkeit | hoch | mittel | **hoch (je Slice)** |
| Performance | Filter je Record | vernachlässigbar | Filter je Record |
| Erweiterbarkeit | gering | hoch | hoch |

**Begründung für C:** A allein kann Vault-/Clipboard-Prosa nicht zuverlässig erkennen
(Regex gegen Fließtext ist chancenlos) — das ist keine Garantie, sondern eine Vermutung.
B allein lässt `uvicorn`/`httpx`/Legacy ungeschützt. C gibt dem eigenen Code die
**strukturelle** Allowlist-Garantie und legt zusätzlich ein Netz unter alles, was nicht
migriert ist — und ist als einziges Slice-für-Slice rückrollbar.

## 9. Getroffene Entscheidungen

| # | Entscheidung |
|---|---|
| **D1** | **Variante C (Hybrid)**: semantische Allowlist-Events + zentraler Schutzfilter |
| **D2** | Scope **Python-Runtime**; Launcher/PS1 dokumentiert, eigener späterer Slice |
| **D3** | **Keine rohen privaten Inhalte auf irgendeinem Level** (SI-9 wird verschärft) |
| **D4** | **Beide Formate**: menschenlesbar (Default) + JSONL per Schalter, gleiche Felder |
| **D5** | Unbekannte Felder **verworfen** + neutraler Marker (nur Anzahl); Event bleibt sichtbar |
| **D6** | Exceptions: **Typ + Ort immer**; Message/Traceback **redigiert** |
| **D7** | URL → **Schema+Host**; Pfade → Basename/Marker; App-/Profil-IDs erlaubt |
| **D8** | **Statischer, datenfreier Fallback**; Logging bricht den Ablauf nie ab |
| **D9** | Modul **importsicher**; Konfiguration einmalig am Startpfad; Test-Sink injizierbar |
| **D10** | Rotation/Aufbewahrung **unverändert**; **kein** neuer Sink/FileHandler/Dependency |
| **D11** | Schema strukturell erweiterbar — **keine** Korrelations-ID festgelegt/benannt/implementiert |
| **D12** | Test-Seam = öffentliche Schnittstelle + In-Memory-Sink; Assertions am **formatierten Output** |

## 10. Zielmodul und öffentliche Schnittstelle

Vorgesehen: **`obslog.py`** (Name im Slice final; „log"/"logging" kollidiert mit stdlib).
Konzeptionell — die finalen Signaturen bleiben der Implementierung überlassen:

```python
obslog.event(name, **fields) -> None      # das EINZIGE Emit-Interface
obslog.configure(sink=None, fmt="text"|"jsonl", level=...) -> None   # nur am Startpfad
obslog.install_protection() -> None       # zentraler Filter fuer Legacy/Dritte
```

- `name` ist ein **benanntes Ereignis** aus einer geschlossenen Menge
  (z.B. `action.started`, `action.finished`, `settings.saved`, `browser.fallback`,
  `config.migrated`, `app.launched`).
- `**fields` akzeptiert **nur** Felder der Allowlist **dieses** Events; alles andere wird
  verworfen (D5).
- **Kein** Freitext-Payload-Parameter. Es gibt keine Möglichkeit, roh zu loggen.
- Der Test-Seam ist genau diese Schnittstelle plus ein injizierbarer Sink — **nicht** die
  privaten Redaction-/Regex-Helfer.

## 11. Ownership und Lifecycle

Logging ist **prozessweit**, nicht pro Runtime (D9). Das Modul hält keinen
Runtime-Zustand. `configure()`/`install_protection()` laufen **genau einmal** am
Startpfad (`server.__main__` bzw. Composition Root); Tests konfigurieren stattdessen
einen In-Memory-Sink. Kein Hintergrund-Task, kein eigener Lifecycle, kein Handler beim
Import.

## 12. Import-Sicherheit

Wie RFC-0002: der **Import** des Moduls erzeugt **keinen Handler, keine Datei, keine
I/O, keinen Task** und ändert die Root-Logger-Konfiguration nicht. `import server` bleibt
seiteneffektfrei. Ein Import-Sicherheitstest (Subprozess) gehört in den Umsetzungs-Slice.

## 13. Event-Schema

Ein Operational Log Event besteht aus:

| Teil | Herkunft | Beispiel |
|---|---|---|
| `ts`, `level`, `logger` | Framework | unverändert |
| `event` | Aufrufer (geschlossene Menge) | `action.finished` |
| Felder | **Allowlist je Event** | `action="CLIPBOARD"`, `result_len=412`, `duration_ms=88` |
| `dropped_fields` | Modul (nur wenn >0) | `2` (nur Anzahl, nie Name/Wert) |

Das Schema ist **strukturell erweiterbar** (weitere reservierte Metadatenfelder je Event
möglich) — Prompt 12 legt dafür **keine** ID fachlich fest (D11).

## 14. Erlaubte Felder und Redaction-Regeln

| Feldtyp | Regel |
|---|---|
| Zähler/Längen/Dauern/Statuscodes/Booleans | erlaubt, roh |
| Action-Typ, App-ID, Profil-ID/-Name, Monitor/Zone, Event-Name | erlaubt (`local`) |
| **URL** | **nur `schema://host`** — Query und Pfad entfallen (D7, behebt L1) |
| **Dateipfad** | nur Basename oder neutraler Marker; nie Vault-/Nutzerpfad |
| **Freitextinhalt** (Nutzereingabe, LLM-Antwort, Clipboard/Vault/Screen/Inbox) | **kein erlaubtes Feld** — stattdessen `*_len`/`*_kind` |
| **Secrets/Token/Auth-Header/Config-Werte** | **nie**, auf keinem Level |
| Backup-Pfad/-Inhalt | **nie** (RFC-0003 §29) |
| unbekanntes Feld | verworfen + `dropped_fields`-Zähler (D5) |

## 15. Fail-closed-Verhalten

- **Default geschlossen:** Was nicht auf der Allowlist steht, erscheint nicht. Ein neues
  Feld ist unsichtbar, bis es bewusst erlaubt wird.
- **Redaction-Fehler:** Wirft die Redaction/Formatierung, wird eine **feste, datenfreie**
  Ersatzzeile ausgegeben (Event-Name + Fehlertyp, **keine** Ursprungsdaten). Es gibt
  keinen Pfad, auf dem ein Fehler die Rohzeile ausgibt (D8).
- **Logging-Fehler brechen nie den Geschäftsablauf ab** — jeder Emit ist gekapselt.
- **Schutzfilter:** Legacy-/Drittanbieter-Records durchlaufen den zentralen Filter; auch
  dessen Fehler führen zur datenfreien Ersatzzeile, nie zum Durchreichen.

## 16. Exception- und Traceback-Policy (D6)

- **Immer:** Exception-**Typ** und **Codeort** (Modul/Funktion/Zeile).
- **Nie roh:** die Exception-**Message** (Beleg L5: sie trägt Sentinel-Inhalt) — sie wird
  redigiert bzw. auf Typ reduziert.
- **Traceback-Frames** (Datei/Zeile/Funktion) sind erlaubt, **lokale Variablen nie**.
- `exc_info=True` im Anwendungscode wird durch die Event-Schnittstelle ersetzt; im
  Schutzfilter wird `exc_text` nach denselben Regeln behandelt.

## 17. Legacy-/Drittanbieter-Adapter

Ein zentraler `logging.Filter` am Root-Handler (D1/C):

- greift für `uvicorn`, `uvicorn.access`, `httpx`, `anthropic`, `playwright` und jeden
  noch nicht migrierten `jarvis.*`-Aufruf;
- kürzt URLs auf Schema+Host, behandelt `exc_text` nach §16 und wendet
  Secret-/Token-Muster an;
- ist ein **Netz, keine Garantie** — die Garantie entsteht durch die Allowlist-Events.
  Das ist eine bewusst benannte Grenze (§25).

## 18. Log-Sinks und Formate (D4/D10)

- **Default:** eine menschenlesbare Zeile — der Launcher-Tail (`read_log_tail`, 15 Zeilen
  im UI) und die gewohnte Diagnose bleiben unverändert brauchbar.
- **JSONL:** per Umgebungsschalter; **dieselben** Felder ⇒ **dieselbe** Redaction.
- **Kein neuer Sink:** weiterhin stderr; die Persistenz macht wie bisher der Launcher.
  **Kein** `FileHandler`, **keine** neue Abhängigkeit.

## 19. Rotation und Aufbewahrung (D10)

Unverändert: `jarvis-launcher.pyw` rotiert bei ~1 MB mit 3 Backups; `jarvis-launch.log`
(PS1) wächst unbegrenzt. Beide sind gitignored. Eine explizite Retention-/Rotations-Policy
gehört zum Launcher-Slice (D2) und wird hier **nicht** entschieden.

## 20. Migrationsslices (für Prompt 13)

| Slice | Inhalt |
|---|---|
| **0** | Charakterisierung + Redaction-Vertrag: Sentinel-Fixtures, erste rote Tests am Sink-Output, reine Redaction-Regeln — **kein** produktiver Sink |
| **1** | Zentrales Modul (`obslog`): `event`/`configure`, Allowlist, Fail-closed-Fallback, importsicher |
| **2** | Ownership: Konfiguration am Startpfad statt `basicConfig` beim Import; In-Memory-Sink für Tests |
| **3** | Höchstes Risiko zuerst: `server.py`, `assistant_core.py`, `actions.py` (behebt L2–L4) |
| **4** | Externe Grenzen: `browser_tools` (behebt **L1**), `tts`, `memory`, `clipboard_tools`, `configuration`, `app_launcher` |
| **5** | Legacy-/Drittanbieter-Schutzfilter (`uvicorn`/`httpx`/…) + `exc_text`-Policy |
| **6** | Fault-Injection, Datenschutz- und Regressionstests (§23) |
| **7** | Dokumentation + CI-Gates; **SI-9-Verschärfung** in SECURITY_REQUIREMENTS |
| **(8)** | *Optional, eigener Entscheid:* Launcher/PowerShell (D2) |

## 21. Rückrollpunkte

Jeder Slice ist ein eigener, grüner, einzeln revertierbarer Commit. Vor jedem Slice ist
der letzte grüne Stand (Suite + Smoke) der Rückrollpunkt. Slice 3/4 sind pro Modul
revertierbar; der Schutzfilter (Slice 5) ist unabhängig von den Events revertierbar —
genau deshalb wurde C gewählt.

## 22. Öffentlicher Test-Seam (D12)

- **Seam:** die öffentliche Logging-Schnittstelle + ein **injizierbarer In-Memory-Sink**.
- **Assertions am vollständig formatierten Sink-Output** — in beiden Formaten.
- **Nicht** getestet werden private Regex-/Filter-/Formatter-Helfer.
- Sentinels: synthetisch, auch **verschachtelt** und **in URLs**; Exceptions mit
  Sentinel-Inhalt.
- Geprüft wird zusätzlich: sichere semantische Metadaten **bleiben erhalten**;
  Logging-Ausfälle brechen den Ablauf **nicht** ab; Redaction-Ausfälle geben **nie**
  Rohdaten aus; **Import-Sicherheit** (Subprozess).

## 23. Fehler- und Fault-Injection-Plan

| Injizierter Fehler | Erwartung |
|---|---|
| Redaction wirft | datenfreie Ersatzzeile; kein Rohwert; Ablauf läuft weiter |
| Formatter wirft | wie oben |
| Sink wirft (Datei/Stream kaputt) | Ablauf läuft weiter; kein Rohwert |
| Unbekanntes Feld | verworfen + `dropped_fields`; Event sichtbar |
| Feld mit falschem Typ | verworfen wie unbekannt |
| Exception mit Sentinel-Message | Typ+Ort sichtbar, Sentinel **nicht** |
| Drittanbieter-Record mit Sentinel-URL | nur Schema+Host |
| JSONL-Serialisierung wirft | datenfreie Ersatzzeile |

## 24. Kompatibilitätsanforderungen

Menschenlesbare Launcher-Diagnose bleibt (D4) · `read_log_tail` bleibt nutzbar ·
`JARVIS_LOG_LEVEL` bleibt · keine neue Abhängigkeit · keine Änderung an REST-, WS-,
Config-, Memory- oder UI-Verträgen · Import-Sicherheit (RFC-0002) · Composition-Root-
Besitz (RFC-0002) und Configuration-Single-Writer (RFC-0003) unberührt · CI-Ausgaben
bleiben lesbar.

## 25. Risiken und Gegenmaßnahmen

- **Der Schutzfilter ist ein Netz, keine Garantie** (§17): Drittanbieter könnten Inhalte
  in Formen loggen, die kein Muster erkennt. Minderung: eigener Code migriert auf
  Allowlist-Events; Drittanbieter-Level konservativ (z.B. httpx auf WARNING).
- **Diagnoseverlust** durch strengere Redaction (D3/D6): Minderung durch aussagekräftige
  Metadaten (Längen, Typen, Dauern, Codeort) statt Rohtext.
- **Doppelpflege** von Allowlist und Aufrufern: Minderung durch geschlossene Event-Menge
  und Tests am Sink-Output.
- **Bestehende Logdateien** enthalten weiterhin Altinhalte aus der Zeit vor der Migration;
  dieses RFC löscht/bereinigt sie **nicht** (kein Scope) — akzeptiertes Restrisiko.
- **Launcher/PS1** bleiben vorerst ungeregelt (D2) — bewusst benannt.

## 26. Freigabe-Gates für die spätere Implementierung

- **Je Slice:** gezielter Test rot→grün; volle Suite grün; Smoke Exit 0, 0 unerwartete
  Skips; `git diff --check` sauber.
- **Vor Slice 5 (Schutzfilter):** eigener Code der Hochrisikopfade migriert.
- **Vor Abschluss:** alle sechs belegten Leckvektoren (L1–L6) haben je einen Test am
  Sink-Output, der ohne den Fix rot ist; Import-Sicherheitstest grün; Hosted Windows CI
  (Fast + Browser) grün.
- **Prompt 12 selbst:** ändert **keinen** Produktionscode, keine Tests, keine Workflows,
  keine Dependencies — nur dieses RFC und eine Statusnotiz.
