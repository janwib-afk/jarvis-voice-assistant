# RFC: Action als deep module (Selbstbeschreibung + Selbstausführung)

## Status

**Accepted for incremental implementation** (2026-07-13).

Grundlage der Annahme: In der Grilling-Session (Prompt 4) hat der Nutzer die
Entscheidungen D1–D4 einzeln bestätigt und anschließend ausdrücklich delegiert
(„Folge ab jetzt immer deiner Empfehlung bis du fertig bist"). Die Variantenwahl
(Variant A) erfolgt auf dieser ausdrücklichen Delegation; beide Varianten sind in
diesem RFC ernsthaft ausgearbeitet. Kein Produktionscode wurde geändert.

## Zusammenfassung

Das Wissen über eine **Action** ist heute dreifach repräsentiert und über zwei
Module verstreut: Metadaten (`actions.ActionSpec`/`REGISTRY`), Verhalten
(`assistant_core.execute_action`, ein 24-Zweig-`if/elif`) und Prompt-Beschreibung
(hardcodiert in `assistant_core.build_system_prompt`). Dieses RFC vertieft die Action
zu einem **deep module**, das sich **selbst beschreibt und selbst ausführt**, hinter
einem kleinen, einheitlichen interface. Der Dispatcher wird ein dünner Lookup, der
System-Prompt wird *aus* den Actions erzeugt statt sie zu duplizieren. Das
`[ACTION:…]`-Wire-Format bleibt über den bestehenden `parse_action`-adapter
unverändert. Der Umbau ist vertikal (eine Action nach der anderen) und rückrollbar.

## Problem und Codeevidenz

| Repräsentation | Ort | Beleg |
|---|---|---|
| Metadaten (label, payload-Regel, risk, timeout, is_url/is_browser, speaks_result, summary_task, summary_max_tokens) | `ActionSpec` + `REGISTRY` | `actions.py:18–123` |
| Verhalten | `execute_action` — `if/elif` auf `action.type`, 24 Zweige | `assistant_core.py:452–563` |
| Prompt-Beschreibung | hardcodierter Text je Action | `assistant_core.py:208–222`, Launcher-Block `167–190` |
| abgeleitete Klassifikation | `CONFIRM_ACTIONS`/`SPEAK_RESULT_ACTIONS`/`BROWSER_ACTIONS`/`URL_ACTIONS` | `actions.py:126–139` |
| Konsum der Metadaten | Timeout/Cancel/Summary/Speak-Branch | `run_action_and_respond`, `assistant_core.py:584–650` |

**Beobachtete Friktion:** Eine neue oder geänderte Action fasst 3–4 Stellen in zwei
Modulen an (Registry-Eintrag, `if/elif`-Zweig, Prompt-Absatz, ggf. Set-Zugehörigkeit).
Tests, die eine Action prüfen, müssen den Weg über `process_message` nehmen und
Modul-Globals patchen (`ai`, `conversations`). Der System-Prompt dupliziert die
Registry als Fließtext — zwei Quellen der Wahrheit, die auseinanderdriften können.

## Domainbegriffe

Kanonisch aus `CONTEXT.md` (unverändert): **Action**, **ActionSpec**, **Confirmation**,
**Message**, **Conversation Session**, **Research**, **Browser Task**. Zielbegriff
**Capability** bleibt „noch nicht implementiert" (Phase 5) — dieses RFC bereitet den
seam nur vor. In der Grilling-Session wurde **kein neuer Domainbegriff** geklärt;
`CONTEXT.md` wird daher nicht verändert. Die in diesem RFC verwendeten Begriffe
„Selbstbeschreibung", „Selbstausführung", „Ausführungskontext" und „Ausgabevertrag"
sind **Architektur-**, keine Domainbegriffe und gehören bewusst nicht in `CONTEXT.md`.

## Aktueller Zustand

- **Parsing (bleibt):** `parse_action` (`actions.py:210–245`) validiert die untrusted
  LLM-Ausgabe: unbekannter Typ, fehlender Payload, ungültige URL → kein Ausführen,
  nur `spoken_text`. Liefert `(spoken, Action|None, error|None)`.
- **Dispatch (wird vertieft):** `execute_action(action, session_id)` gibt einen
  rohen Ergebnis-String zurück; liest `ai`/`conversations`-Globals; delegiert an
  `browser_tools`/`memory`/`app_launcher`/`screen_capture`/`clipboard_tools` und die
  `_voice_*`-Helfer.
- **Orchestrierung (bleibt außen):** `run_action_and_respond` setzt Timeout durch
  (`asyncio.wait_for(…, spec.timeout)`), behandelt Cancel, sendet WS-`action`-Events,
  entscheidet „sprechfertig (`speaks_result`)" vs. „Zusammenfassungs-LLM", macht den
  RESEARCH-Autosave und TTS.
- **Prompt (wird vertieft):** `build_system_prompt` fügt pro Action einen fixen
  Textabsatz ein und liest 6 Prozess-Globals + `app_launcher`/`memory`.

## Bestehende Verhaltensinvarianten

Diese Verträge **müssen** während der gesamten Migration erhalten bleiben:

1. **`[ACTION:…]`-Wire-Format:** Regex `ACTION_PATTERN` (`actions.py:15`) und der
   `parse_action`-Vertrag (Rückgabe-Tripel, payload-Regeln, URL-Normalisierung,
   Unknown-Type-Handling) bleiben byte-genau.
2. **22 Action-Typen** mit exakt heutigen Typ-Strings.
3. **Confirmation-Fluss:** `risk="confirm"` → `pending_confirm` → `is_confirmation` →
   Ausführung/Abbruch (aktuell nur `MEMORY_FORGET`).
4. **Stop/Cancel-Semantik:** Worker/Queue in `server.py:142–211`, `is_stop_command`
   unverändert; Cancel während `execute` wirft `CancelledError` durch.
5. **Ausgabevertrag:** `speaks_result`-Actions werden **wörtlich** gesprochen; alle
   anderen laufen durch den Zusammenfassungs-LLM mit `summary_task`/`summary_max_tokens`.
   `OPEN` gibt früh zurück (keine Zusammenfassung). RESEARCH hängt Quellen an und
   speichert in den Brain Dump.
6. **WS-Frames** (`response`, `action`, `error`, `stop`, `health`) unverändert.
7. **`/health` und `/dashboard/state`** lesen weiter `DATA_LOADED`/`LAST_REFRESH`/
   `TASKS_INFO`/… — von diesem RFC nicht berührt.
8. **Sicherheits-Policies:** `OPEN` nur `http`/`https`; `APP_OPEN` nur Allowlist;
   kein Shell aus Modellausgabe; Confirmation vor destruktivem `MEMORY_FORGET`.
9. **Config-/Memory-Dateiformate** unverändert.
10. **System-Prompt-Text:** bis zur bewussten Umstellung (Slice P) **byte-identisch**
    (Golden-Test), damit sich das LLM-Verhalten nicht unbemerkt ändert.

## Ziele

- Spec + Verhalten + Prompt-Beschreibung je Action an **einer** Stelle (locality).
- `execute_action` wird ein dünner Lookup; der `if/elif`-Router verschwindet.
- System-Prompt wird aus den Actions erzeugt (eine Quelle der Wahrheit).
- Action über **ein** interface testbar, ohne Modul-Globals zu patchen.
- Den seam schaffen, an dem Phase 5 (Capability/Policy) andockt.

## Nicht-Ziele

- **Kein** Capability-Lebenszyklus (`validate/preview/authorize/verify`) — Phase 5.
- **Keine** Änderung an Orchestrierung, Conversation-Session-Besitz (Kandidat 03),
  Composition Root (Kandidat 02), Provider-Deepening (Kandidat 04).
- **Keine** Bewegung der fremden Policies in `actions.py` (Origin, Stop, URL,
  Inbox-Kategorie, Place-Parsing).
- **Keine** Änderung an `[ACTION:…]`, REST-Pfaden, WS-Frames, Config-/Memory-Formaten.
- **Keine** Job-Engine, kein Scheduler, kein Outbox/Saga.

## Einschränkungen

- Windows / CPython 3.10+ (SYSTEM_CHARTER).
- Standardtests kosten 0 Provider (QUALITY_BASELINE); LLM/TTS/Browser gemockt.
- `core.autocrlf=true` ohne `.gitattributes` → Slices klein halten, damit Diffs
  lesbar bleiben (Zeilenenden-Risiko aus CURRENT_STATE §12).
- Nur vertikale, einzeln rückrollbare Slices; kein Big-Bang.

## Betrachtete Varianten

Beide Varianten teilen die Grilling-Constraints D1–D4: Begriff „Action" bleibt; die
Action besitzt beschreiben + ausführen + deklarative Metadaten; Orchestrierung bleibt
außen; `parse_action` bleibt adapter; expliziter Ausführungskontext für
LLM/Session/Persist-Hook, direkte Deps auf die Capability-Module.

### Variant A — Deklarativer Registry-Eintrag + `execute`-Funktion (datenorientiert)

- **Konzeptionelles interface:** Der heutige `ActionSpec` wächst um zwei Elemente:
  eine **Selbstbeschreibung** (Prompt-Text bzw. kleine Funktion, die ihn erzeugt) und
  eine **`execute`-Referenz** (`async execute(payload, ctx) -> str`). `REGISTRY` bleibt
  `dict[str, Action]`. Dispatch = `REGISTRY[type].execute(payload, ctx)`.
- **Verborgene Implementation:** die heutigen `if/elif`-Zweigkörper werden je zur
  `execute`-Funktion ihres Eintrags.
- **Zustands-/Ressourcenbesitz:** kein Zustand je Action; `ctx` pro Aufruf.
- **Reale Adapter:** LLM (Anthropic-prod + Fake-test) via `ctx`; Capability-Module direkt.
- **Betroffene Aufrufer:** `execute_action` → Lookup; `build_system_prompt` iteriert
  die Beschreibungen; abgeleitete Sets bleiben (aus den Einträgen berechnet).
- **Depth:** moderat — interface = Eintrag + Funktion; wenig Zeremonie.
- **Locality:** hoch — Spec + Verhalten + Beschreibung je Eintrag beisammen.
- **Leverage:** Dispatcher + Prompt + Summary lesen dieselbe Struktur.
- **Testoberfläche:** `action.execute(payload, fake_ctx)`; Beschreibung als String prüfbar.
- **Kompatibilität:** `parse_action` unverändert; gleiche Typ-Strings; Sets erhalten.
- **Migrationsrisiko:** niedrig — kleinster Delta zu heute (`ActionSpec` existiert schon).
- **Rückrollbarkeit:** hoch — Eintrag-für-Eintrag unabhängig.
- **Sicherheitsauswirkung:** Metadaten können Datenklasse/Wirkungsklasse als
  deklarative Felder tragen (Phase-5-Vorbereitung), ohne sie jetzt durchzusetzen.

### Variant B — Action-Protokoll / deep module je Action (objektorientiert)

- **Konzeptionelles interface:** jede Action ist ein Objekt/Modul, das ein
  einheitliches Protokoll erfüllt: `describe()`, `execute(payload, ctx)`, plus
  Metadaten als Attribute. Registrierung in eine Sammlung von Action-Objekten.
- **Verborgene Implementation:** jede Action ein eigenes Modul mit potenziellen
  **internen** seams (z.B. RESEARCH strukturiert seinen Mehrquellen-Lauf intern).
- **Zustands-/Ressourcenbesitz:** Action-Objekte sind zustandslose Singletons oder
  werden am Composition Root mit Deps konstruiert; `ctx` pro Aufruf.
- **Reale Adapter:** LLM via `ctx` oder Konstruktor; Capability-Module direkt.
- **Betroffene Aufrufer:** wie A (Dispatcher-Lookup, Prompt-Iteration).
- **Depth:** höher — jede Action ein echtes deep module mit eigenem interface.
- **Locality:** höchste — jede Action vollständig eigenständig (eigenes Modul).
- **Leverage:** einheitliches Protokoll über alle 22 Actions.
- **Testoberfläche:** Action-Objekt mit Fakes instanziieren, `execute` prüfen.
- **Kompatibilität:** identische Wire-Format-Erhaltung wie A.
- **Migrationsrisiko:** moderat — mehr Struktur/Zeremonie (Objekt je Action).
- **Rückrollbarkeit:** je Action unabhängig, aber größerer Einzelschritt.
- **Sicherheitsauswirkung:** stärkster Phase-5-Sitz — das Objekt wächst später
  `validate/preview/authorize/verify` als Methoden.

### Substanzieller Unterschied

Zustands-/Ressourcenbesitz (zustandsloser Eintrag vs. ggf. konstruiertes Objekt),
interface-Fläche (Datensatz + freie Funktion vs. einheitliches Protokoll/Objekt),
Erweiterbarkeit für Phase 5 (Feld hinzufügen vs. Methode hinzufügen), Zeremonie/
Migrationsgröße (minimal vs. moderat), Depth (moderat vs. höher). Kein bloßes
Umbenennen.

## Entscheidung

**Gewählt: Variant A** (deklarativer Eintrag + `execute`-Funktion), auf ausdrückliche
Delegation des Nutzers.

Begründung: kleinster, am besten rückrollbarer Delta (Masterplan „kein Big-Bang",
ADR-0003-Geist „minimale Seams zuerst"); die Depth ist **jetzt** ausreichend, weil die
belegte Friktion (Dreifach-Repräsentation) allein durch Co-Location von Spec +
Beschreibung + `execute` verschwindet. Die meisten Actions sind heute dünne
Delegationen (ein Aufruf an `browser_tools`/`memory`) — Variant B's per-Action-Objekte
brächten Kapselungs-Zeremonie, deren Nutzen (interne seams) erst bei reicheren Actions
greift („one adapter = hypothetical, two = real" auch auf Modulebene). **Promotionspfad:**
Wenn Phase 5 reichere per-Action-Kapselung braucht, kann ein Eintrag mechanisch und
vertikal zu einem Objekt (Variant B) promotet werden — die `execute`-Funktionen sind
dann bereits isoliert und getestet, also kein Redo.

## Zielarchitektur

- Eine **Action** ist ein deep module: kleines interface (beschreiben + ausführen +
  deklarative Metadaten), große verborgene Implementation (das heutige Zweigverhalten).
- Die **Registry** ist die Sammlung dieser Module (weiter `dict[str, Action]`).
- Der **Dispatcher** (`execute_action`) wird ein Lookup + Aufruf.
- Der **System-Prompt** wird aus den Selbstbeschreibungen erzeugt.
- Die **Orchestrierung** (Timeout, Cancel, Summary, TTS, WS-Events, Confirm, Stop)
  bleibt unverändert außen und liest die deklarativen Metadaten.
- `parse_action` bleibt der `[ACTION:…]`-**adapter** am seam zwischen LLM-Text und Action.

## Interface

Konzeptionell (finale Signaturen bleiben der Implementierung überlassen):

- **Metadaten** (deklarativ, wie heute `ActionSpec`): `type`, `label`, payload-Regel,
  `is_url`, `is_browser`, `risk`, `timeout`, Ausgabevertrag (`speaks_result`),
  `summary_task`, `summary_max_tokens`. **Vorbereitend (nicht durchgesetzt):** optionale
  Datenklasse/Wirkungsklasse-Felder für Phase 5.
- **Selbstbeschreibung:** liefert den Prompt-Absatz dieser Action (statisch oder aus
  Kontext, z.B. verfügbare Apps/Profile für die Launcher-Actions).
- **Ausführung:** `execute(payload, ctx) -> str` — nimmt den validierten Payload und
  einen **Ausführungskontext**; gibt das rohe Ergebnis zurück (die Orchestrierung
  fasst zusammen/spricht).
- **Ausführungskontext (`ctx`):** kapselt die querschnittlichen Abhängigkeiten —
  LLM-Zugriff, lesenden Session-/Verlaufszugriff (für `SESSION_SUMMARY`) und den
  `PERSIST_LAUNCHER`-Hook. **Nicht** im ctx: die stabilen Capability-Module.

Die **Testoberfläche ist genau dieses interface** — nicht die Modul-Globals.

## Verborgene Implementation

Hinter dem interface liegen: die heutigen Zweigkörper (`execute_action`) als je eigene
`execute`; die aktionsspezifischen Prompt-Absätze als Selbstbeschreibung; die
`_voice_*`-Helfer als Implementation der Launcher-Actions. Nicht am interface sichtbar:
welche Capability-Module eine Action nutzt, wie RESEARCH mehrere Quellen liest, wie der
Launcher-Zustand persistiert wird.

## Zustands- und Ressourcenbesitz

- Actions sind **zustandslos** (Variant A). Kein Zustand wird erzeugt/verworfen.
- **Kontext-Gültigkeit:** `ctx` gilt **pro Nachricht/Ausführung** (request-scoped) und
  wird von der Orchestrierung gestellt, nicht von der Action gehalten.
- **Ressourcen:** LLM-/HTTP-/Browser-Ressourcen bleiben im Besitz des Servers
  (Composition Root, Kandidat 02) — dieses RFC ändert daran nichts; es reicht den
  LLM-Zugriff nur als `ctx`-Bestandteil durch.
- **Disconnect/Stop/Shutdown:** unverändert — die Orchestrierung (Worker/Queue,
  `end_session`, Shutdown-Hook) besitzt diese Abläufe; Actions sind daran unbeteiligt.

## Adapter und Abhängigkeitsrichtung

- **Realer seam (zwei Adapter):** LLM — Anthropic-prod + Fake-test existieren bereits
  (`baseline_server`/Test-Stubs) → gerechtfertigt, injiziert via `ctx`.
- **Direkte Abhängigkeit (kein seam):** `browser_tools`, `memory`, `app_launcher`,
  `screen_capture`, `clipboard_tools` — bereits tiefe Module mit eigenem Test-Seam; ein
  zusätzlicher Port wäre hypothetisch (ein Adapter) und reine Indirektion.
- **Richtung:** Actions hängen nach innen an einem kleinen `ctx`-Vertrag und nach außen
  an stabilen Capability-Modulen; die Orchestrierung hängt an der Action-Registry, nicht
  umgekehrt.

## Lifecycle

Keine neuen Lebenszyklen. Registry wird beim Import aufgebaut (wie heute); Actions
leben prozessweit als unveränderliche Einträge; `ctx` entsteht und vergeht pro
Nachricht.

## Fehler-, Timeout- und Cancel-Semantik

Unverändert und außerhalb der Action:

- **Timeout:** `asyncio.wait_for(execute(...), spec.timeout)` in der Orchestrierung.
- **Cancel:** „Stopp" cancelt den Nachrichten-Task; `CancelledError` propagiert durch
  `execute`; die Orchestrierung markiert die Aktionshistorie „abgebrochen".
- **Teilfehler:** `execute` gibt einen Fehler-String zurück oder wirft; die
  Orchestrierung baut das strukturierte `error`-Frame (Komponente `browser`/`action`).
- **Kein** Idempotency-/Retry-/Outbox-Verhalten (Phase 6, außerhalb).

## Nebenläufigkeit

Actions je WS-Session laufen **sequenziell** (Worker/Queue) — unverändert. Actions
halten keinen geteilten mutablen Zustand, daher keine neuen Races. Die
Launcher-Persistenz (`PERSIST_LAUNCHER`) behält ihr heutiges Verhalten inkl. des
bestehenden Lost-Update-Fensters (das ist Kandidat 05, **nicht** dieses RFC).

## Security- und Datenschutzinvarianten

- **Untrusted Eingabe:** `parse_action` bleibt der validierende adapter (Typ/Payload/
  URL); nur validierte `Action`-Objekte erreichen `execute`.
- **Wirkungsgrenzen:** `OPEN` nur `http`/`https`; `APP_OPEN` Allowlist; `MEMORY_FORGET`
  Confirmation; kein Shell aus Modellausgabe — alle unverändert.
- **Secrets/Redaction:** Actions verarbeiten keine Secrets; Logging-Regeln unverändert
  (private Inhalte nur DEBUG).
- **Phase-5-Vorbereitung:** Datenklasse/Wirkungsklasse dürfen als deklarative Metadaten
  ergänzt werden, werden aber **nicht** durchgesetzt (kein Vorgriff auf das Threat Model
  aus Prompt 5).
- **Offen (nicht dieses RFC):** untrusted Web-/Screen-/Clipboard-/Vault-Inhalte fließen
  weiterhin ins LLM — Phase-2-Thema.

## Testoberfläche

- **Neu:** je Action ein Test gegen ihr interface — `execute(payload, fake_ctx)` +
  Selbstbeschreibung als String; **kein** Patchen von `ai`/`conversations`-Globals.
- **Bleibt unverändert:** `test_actions.py` (parse_action, URL, Confirm/Stop, Place,
  Inbox-Kategorie, Origin), da `parse_action`/Policies nicht angefasst werden.
- **Schützt die Migration:** (1) **Parität** — pro Action ein Vergleich, dass die neue
  `execute` dasselbe liefert wie der alte Zweig; (2) **Prompt-Golden** — der generierte
  System-Prompt ist byte-identisch zum heutigen, bis Slice P ihn bewusst umstellt;
  (3) bestehende Integration (`test_integration_research`, `test_confirm_flow`,
  `test_voice_launcher`) läuft unverändert weiter.

## Kompatibilitätsstrategie

Ausdrücklich pro Format:

- **REST-Pfade:** unverändert — keiner wird berührt.
- **WS-Frames:** unverändert (`response`, `action`, `error`, `stop`, `health`, …).
- **`[ACTION:…]`:** über `parse_action` als **permanenten** adapter erhalten
  (kein Entfernungskandidat).
- **Config-Format:** unverändert.
- **Memory-Format:** unverändert.
- **Erforderliche Legacy-Adapter:** (a) `parse_action` — permanent; (b)
  **Dispatcher-Shim** — temporär: routet migrierte Typen zum neuen Pfad, nicht
  migrierte zum alten `if/elif`; (c) **Prompt-Golden-Gerüst** — temporär.
- **Alt-vs-Neu-Vergleich:** Paritätstests je Action (Dispatch-Ergebnis-Gleichheit) +
  Prompt-Golden-Test.
- **Adapter-Entfernung:** der Dispatcher-Shim darf erst weg, wenn **alle 22** Actions
  migriert sind und Contract- + Browser-Abdeckung grün ist (Slice C).
- **Deprecation-Signale:** keine externen nötig (interner Refactor; `[ACTION:…]` bleibt).

## Migrationsplan

Vertikale, einzeln rückrollbare Slices. Verifikation je Slice mindestens:
`python -m unittest discover -s tests` (grün, 0 unerwartete Skips) und
`python scripts/smoke-test.py` (Exit 0); nach Prompt-Slices zusätzlich
`verify_phase4`/`verify_phase5`.

**Slice 0 — Seam & Shim (Gerüst).**
- Zielverhalten: eine migrierte Beispiel-Action (empfohlen `SESSION_SUMMARY`, rein,
  liest Verlauf via `ctx`) läuft über den neuen Pfad, Ergebnis identisch zum alten Zweig.
- Geschützte Invarianten: alle (Dispatch-Ergebnis identisch).
- Öffentliche Test-Seam: das Action-interface (`execute(payload, ctx)`).
- Erster fehlschlagender Test: „neuer Pfad für `SESSION_SUMMARY` liefert = alter Zweig".
- Minimale Grenze: interface + `ctx` + Dispatcher-Shim; genau eine Action migriert.
- Kompatibilitätsadapter: Shim (temp), `parse_action` (permanent).
- Rückrollpunkt: neues Modul entfernen; `if/elif` unangetastet.
- Exit-Kriterium: Parität für die Beispiel-Action grün; Suite/Smoke grün.

**Slices 1…k — Verhalten je Action-Gruppe migrieren.** Gruppen nach Abhängigkeit:
(1) Browser (`SEARCH`/`BROWSE`/`OPEN`/`NEWS`/`RESEARCH`), (2) Memory/Vault
(`INBOX_*`/`MEMORY_*`/`NOTES_RECENT`/`PROJECT_CONTEXT`), (3) Launcher-Voice
(`APP_OPEN`/`PROFILE_*`/`APP_AUTOSTART_*`/`APP_PLACE`), (4) Screen/Clipboard/Session
(`SCREEN`/`CLIPBOARD`/`CLIPBOARD_NOTE`/`SESSION_SUMMARY`).
- Zielverhalten je Slice: die Gruppe läuft über `execute`; Shim routet sie um.
- Invarianten: identisches Dispatch-Ergebnis; Ausgabevertrag (`speaks_result`/Summary/
  `OPEN`-Frühabbruch/RESEARCH-Autosave) unverändert.
- Erster fehlschlagender Test: Action-interface-Test der Gruppe (rot vor Verschiebung).
- Grenze: nur Zweigkörper → `execute` verschieben; Zweig entfernen.
- Rückrollpunkt: Verschiebung je Gruppe revertieren (Shim fällt zurück).
- Exit: Gruppe migriert, Paritätstests grün.

**Slice P — Prompt aus Actions erzeugen.**
- Zielverhalten: `build_system_prompt` erzeugt die Action-Absätze aus den
  Selbstbeschreibungen; Ergebnis **byte-identisch** (Golden-Test), dann bewusste,
  reviewte Umstellung falls gewünscht.
- Invarianten: System-Prompt-Text; `verify_phase4`/`verify_phase5` grün.
- Erster fehlschlagender Test: „generierter Prompt == heutiger Prompt (golden)".
- Rückrollpunkt: zurück auf den hardcodierten String.
- Exit: Golden grün; Prompt-Duplikat entfernt.

**Slice C — Legacy-Cleanup.**
- Zielverhalten: `if/elif`-Dispatcher und hardcodierter Prompt-Block entfernt; Shim
  entfernt. `parse_action` **bleibt**.
- Invarianten: alle; volle Contract-/Browser-Abdeckung.
- Rückrollpunkt: Shim wieder einsetzen (letzter grüner Stand).
- Exit: 0 `if/elif`-Zweige; Prompt vollständig generiert; Suite/Smoke/verify grün.

Keine gleichzeitige Einführung von Capability-Kernel/Job-Engine/Scheduler. Alter und
neuer Pfad laufen nur so lange parallel, bis alle 22 Actions migriert sind.

## Rückrollstrategie

Jeder Slice ist ein eigener, revertierbarer Schritt: der Dispatcher-Shim hält alten und
neuen Pfad gleichzeitig lauffähig, sodass jede einzelne Action-Migration ohne Wirkung
auf die übrigen zurückgenommen werden kann. Vor jedem Slice ist der letzte grüne Stand
(Suite + Smoke) der Rückrollpunkt. Slice C (Legacy-Entfernung) ist erst zulässig, wenn
Parität, Prompt-Golden und Browser-Checks grün sind — davor bleibt der alte Pfad das
Sicherheitsnetz.

## Observability-Anforderungen

- Bestehendes Logging je Action (`logger.info("Action: %s", …)`) bleibt.
- Während der Parität: optionales DEBUG-Log/Abgleich „alt vs. neu" pro Action;
  keine neue externe Observability (strukturierte Logs/Korrelation gehören Phase 11).
- Keine Gesprächsinhalte/Screens/Clipboard in Standardlogs (Charter-Invariante).

## Risiken

- **Prompt-Drift:** unbeabsichtigte Änderung des System-Prompts → Golden-Test byte-genau.
- **Paritätslücken an Randfällen** (`OPEN`-Frühabbruch, `speaks_result`-wörtlich,
  RESEARCH-Autosave, Fehler-String-Formen) → per-Action-Paritätstests; Orchestrierung
  bleibt unverändert.
- **Scope-Creep** in Orchestrierung/Session (Kandidat 03) oder Composition Root
  (Kandidat 02) → in Nicht-Zielen ausgeschlossen.
- **Launcher-Actions** brauchen den `PERSIST_LAUNCHER`-Hook im `ctx`; fehlt er (Tests/
  Standalone), muss die Action denselben sprechbaren Fehler liefern wie heute.
- **Zeilenenden (autocrlf):** große Diffs verschleiern Änderungen → Slices klein halten.

## ADR-Beziehungen

- **Kein neues ADR nötig.** Die drei ADR-Kriterien sind nicht gemeinsam erfüllt: Die
  Entscheidung ist zum jetzigen (Planungs-)Zeitpunkt nicht teuer zurückzunehmen (rein
  dokumentarisch, keine Codeänderung; die Umsetzung ist bewusst inkrementell/rückrollbar),
  und der reale Trade-off (Variant A vs. B) ist in diesem RFC vollständig festgehalten —
  eine separate ADR wäre redundant zum RFC.
- **Kein ADR-Konflikt.** Stützt **ADR 0003** (voller Composition Root Phase 4 —
  dieses RFC greift dem nicht vor) und **ADR 0002** (der LLM-`ctx`-Seam ist mit dem
  Provider-Adapter-Ziel vereinbar). **ADR 0001** unberührt.

## Offene Fragen

- **Form des `ctx`** (getipptes Objekt vs. dict) — Implementierungsdetail, in Slice 0
  zu fixieren; Variant A lässt beides zu.
- **Datenklasse/Wirkungsklasse-Taxonomie** der vorbereitenden Metadaten — bewusst offen
  bis zum Threat Model (Prompt 5).
- **Ob `SESSION_SUMMARY`** den Verlauf über `ctx` (empfohlen) oder einen eigenen
  Session-Port liest — in Slice 0 zu bestätigen; hängt an Kandidat 03, dort aber nicht
  vorwegzunehmen.

## Implementierungs-Gates

- **Je Slice:** gezielter Test rot→grün; volle Suite grün; Smoke Exit 0, 0 unerwartete
  Skips; keine WS-/REST-/Prompt-Regression (nach Prompt-Slice `verify_phase4`/`5` grün).
- **Vor Legacy-Entfernung (Slice C):** alle 22 Actions migriert; Paritätstests grün;
  Prompt-Golden grün (dann bewusst pensioniert); Contract- + Browser-Abdeckung grün.
- **Phase-1-Abschluss:** dieses RFC `Accepted for incremental implementation`; kein
  Produktionscode geändert; alle bestehenden Tests grün.
