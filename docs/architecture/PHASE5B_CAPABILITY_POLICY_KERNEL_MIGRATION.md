# Phase 5B — Capability- und Policy-Kernel: Migrationsverlauf

> Umsetzung von [RFC-0007](RFC-0007-capability-policy-kernel.md) **inklusive Amendment 1**
> (Pilotphase). Dieses Dokument ist das **Ledger**: pro Slice Ziel, Seam, Ausgangsverhalten,
> tatsächlich beobachtetes RED, minimale GREEN-Implementierung, Regressionsergebnis,
> Commit-SHA, Rückrollweg und offene Restrisiken.
>
> **Prompt 19 ist die Pilotphase, nicht die Vollmigration** (Amendment 1 A). Phase 5 ist
> mit diesem Prompt **nicht abgeschlossen**.

---

## Rahmen

| | |
|---|---|
| **Basis-SHA** | `f03e4d63a220e8acd22b24ef3076a828993f7356` (`origin/master`) |
| **Post-Merge-Evidenz der Basis** | Run `29683333214` — Fast `88183275932` success, Browser `88183275901` success |
| **Branch** | `phase-5b-capability-policy-kernel` |
| **RFC** | RFC-0007 + Amendment 1 (2026-07-19, ausdrücklich angenommen) |

### Baseline vor dem ersten Slice (frisch gemessen, 2026-07-19)

| Prüfung | Ergebnis |
|---|---|
| `python -m unittest discover -s tests` | **870 Tests, OK** |
| `python scripts/smoke-test.py` | **Exit 0** — 870 Tests, 0 Failures, 0 Errors, 0 Skips |
| Test-Fixture `tests/fixtures/config.test.json` | `a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` — **bytegleich vor und nach dem Lauf** |
| Persönliche `config.json` | vorhanden, **nicht gelesen, nicht verändert, nicht in Tests verwendet** |
| Arbeitsbaum | nur `.claude/settings.local.json` (Nutzerartefakt) — **nie gestaged** |

### Schutzregeln für alle Slices

- Keine echten Provideraufrufe, kein echtes Netz, keine echten Vault-/Clipboard-/Screen-/
  Desktopinhalte. Nur synthetische Fixtures und kontrollierte Fakes.
- Eingecheckte Fixtures dürfen durch Testläufe **nicht** verändert werden (nach jedem Slice
  per Hash geprüft).
- Keine Visual-Baseline aktualisieren. Legacy- und V1-Wire-Verträge bleiben byte-/shape-exakt.
- Kein Test wird gelöscht, übersprungen oder gelockert, um Grün zu erhalten.
- Nur explizit benannte Dateien werden gestaged — nie `git add .`.

> **Konvention zur Commit-SHA.** Die SHA eines Slices steht erst **nach** seinem Commit
> fest. Sie wird deshalb jeweils im **Folge-Slice** nachgetragen; die SHA des letzten
> Slices trägt der Abschluss-Slice nach. Es wird nicht amendet — die Slice-Historie bleibt
> unangetastet rückrollbar.

---

## Slice 0 — Amendment, Baseline und Ledger

**Ziel.** Das verpflichtende Amendment-Gate einlösen und eine belegte Ausgangslage
festhalten, bevor eine Zeile Produktionscode entsteht.

**Öffentlicher Seam.** Keiner — reiner Dokumentationsslice.

**Ausgangsverhalten.** RFC-0007 war akzeptiert, enthielt aber sechs am Code belegte
Widersprüche (Amendment 1 §A1.0). Der Scope von Prompt 19 war zwischen §24 und §27/§28
uneindeutig; das Wirkungsinventar unterzählte die Summary-LLM-Stufe um Faktor ~2; der
SSRF-Durchsetzungspunkt hätte den Piloten verfehlt; der REST-Pilot war nicht ehrlich
absicherbar; §10 und §11 widersprachen sich offen.

**RED.** Nicht anwendbar — kein Verhalten geändert. Statt eines Tests steht hier die
**Verifikation der sechs Befunde am Code** (Amendment 1 §A1.0), jeder mit Datei- und
Zeilenbeleg. Die Befunde wurden dem Nutzer gebündelt vorgelegt und die Beschlusspunkte
A–G ausdrücklich angenommen.

**GREEN (minimal).** Amendment 1 als eigener Abschnitt in RFC-0007 dokumentiert; der
Statuskopf verweist darauf (Muster von RFC-0006 Amendment 1). Dieses Ledger angelegt.
**Kein Produktionscode, kein Test, kein Workflow geändert.**

**Regression.** Suite 870 grün, Smoke Exit 0, Fixture bytegleich — siehe Baseline oben.

**Commit.** `c09bbe9` — `docs(rfc-0007): record amendment 1 and phase 5b ledger`

**Rückrollweg.** Commit reverten. Da nur Dokumentation entsteht, hat ein Rollback keine
Laufzeitwirkung.

**Offene Restrisiken.** Keine aus diesem Slice. Die durch das Amendment **bewusst offen
gelassenen** Punkte sind: `launcher.profile.delete` (keine serverseitig belegbare
Bestätigung möglich, Amendment 1 §A1.4), DNS-Rebinding ohne IP-Pinning (§A1.3) und die
20 Actions plus neun REST-Routen, die erst Prompt 20 migriert (§A1.1).

---

## Slice 1 — Reiner Capability Contract

**Ziel.** Den Capability Core anlegen: geschlossene Taxonomie, unveraenderlicher Vertrag,
abgeleiteter `tier()`, fail-closed Registry und ein passives `inspect()`. Kein Aufrufer,
keine Wirkung auf die Produktion.

**Oeffentlicher Seam.** `SEAM-CAPABILITY` — `capability.CapabilityContract`,
`capability.Registry` (`get`/`names`/`inspect`), `InputSchema`/`OutputSchema` sowie die
Enums. Geprueft wird ausschliesslich ueber diese Oberflaeche; kein Zugriff auf private
Helfer, keine Call-Count-Assertions.

**Ausgangsverhalten.** Es gab keinen Capability-Vertrag. Die gesamte Autorisierungslogik
war `ActionSpec.risk` mit zwei Werten; die fuenf Datenklassen, sieben Wirkungsklassen,
Scopes und Presence existierten nur in Sicherheitsdokumenten (RFC-0007 §2.2).

**RED (tatsaechlich beobachtet).**
`ModuleNotFoundError: No module named 'capability'` — `tests/test_capability_contract.py`
Zeile 14, beim ersten Lauf von `python -m unittest tests.test_capability_contract`.

**GREEN (minimal).** `capability/__init__.py` (kleine Oberflaeche) und
`capability/_contract.py`. Zwei Konstruktionsentscheidungen tragen die Sicherheitslage:

* `effects`/`reads`/`writes` **ohne Defaults** — Weglassen ist `TypeError` (D2).
* `tier()` **abgeleitet**, kein Feld — `tier=` als Argument ist `TypeError`.

Zusaetzlich strukturell abgesichert: `secret` ist als Datenklasse eines Vertrags nicht
darstellbar (SI-5); die Audit-Felder sind gegen eine geschlossene Allowlist gebunden, so
dass Inhalte, URLs und Preview-Hashes **nicht nennbar** sind; `effects` darf nicht leer
sein; unbekannte Eingabefelder werden abgelehnt statt mitgeschleppt.

**Zwischenbefund (eigener Testfehler, systematisch geklaert).** Der erste
Reinheitstest nutzte `importlib.reload`. Das erzeugte eine **zweite** `EffectClass` im
Prozess, worauf jeder spaetere `isinstance`-Vergleich fehlschlug — 24 Fehler, deren
Ursache im Test lag, nicht in der Implementierung. Fehlermeldung gelesen, Ursache
(Modul-Identitaetsspaltung durch Reload) belegt, Gegenmittel: der Reinheitsnachweis
laeuft jetzt im **Subprozess** mit Fallen auf `open`/`socket`/`getaddrinfo`/`Popen`. Das
ist zugleich der staerkere Nachweis, weil er den allerersten Import erfasst.

**Mutationsnachweis (nicht behauptet, ausgefuehrt).** Sieben gezielte Mutationen an
`_contract.py`, je ein voller Testlauf, Datei danach byte-identisch wiederhergestellt:

| Mutation | Ergebnis |
|---|---|
| Secret-Verbot entfernt | **ROT** |
| `tier()` behauptet immer `TRIVIAL` | **ROT** |
| Duplicate-Name erlaubt | **ROT** |
| Audit-Allowlist entfernt | **ROT** |
| Unknown liefert Fallback statt Fehler | **ROT** |
| leere `effects` erlaubt | **ROT** |
| unbekannte Eingabefelder durchgelassen | **ROT** |

Damit ist der Wirkungs-Zensus nachweislich **nicht vacuous**: eine Herabstufung von
`destructive` erscheint als roter Test im Diff, nicht als stille Feldaenderung (§23).

**Regression.** Suite **903** grün (vorher 870, +33). Fixture
`a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` — bytegleich.

**Commit.** siehe Folge-Slice (Konvention oben).

**Rueckrollweg.** Paket `capability/` und die Testdatei entfernen. Es existiert **kein
Produktionsaufrufer**; ein Rollback hat null Laufzeitwirkung.

**Offene Restrisiken.** Der Wirkungs-Zensus prueft in diesem Slice die **Mechanik** an
einer synthetischen Registry — die vier echten Piloten tragen ihren Zensuseintrag in
ihrem jeweiligen Slice bei (5/7/8/9), damit jeder Slice seinen eigenen Nachweis fuehrt.

---

## Slice 2 — Reiner Policy Kernel

**Ziel.** Genau eine Stelle, an der die Frage "darf diese Wirkung jetzt, aus dieser
Quelle, mit dieser Provenance und dieser Praesenz passieren?" beantwortet wird — rein,
deterministisch, total und reihenfolgeunabhaengig.

**Oeffentlicher Seam.** `SEAM-POLICY` — `capability.decide(contract, request, evidence,
rules)`, `capability.ACTIVE_RULES`, `capability.DATED_RULES`. Keine Assertions auf
Regel-Reihenfolge (die Komposition ist ausdruecklich reihenfolgeunabhaengig), keine
Call-Counts auf `decide`.

**Ausgangsverhalten.** Es gab keine Policy-Funktion. Autorisierung war ueber vier
Produzenten verstreut: `risk="confirm"` (genau eine Action), Token-Pruefung, App-Allowlist
und eine URL-Schema-Pruefung — SI-1 war damit nirgends zentral durchsetzbar.

**RED (tatsaechlich beobachtet).** `Ran 24 tests ... FAILED (failures=1, errors=37)`:
37 Fehler, weil `decide`/`ACTIVE_RULES` nicht existierten, plus **ein echter Mangel der
Sandbox** — `TypeError: cannot set 'now' attribute of immutable type 'datetime.datetime'`
(Python 3.14). Der Reinheitsnachweis ersetzt jetzt die **Klasse** am Modul, statt eine
Methode zu patchen; damit deckt er `datetime.datetime.now()` tatsaechlich ab.

**GREEN (minimal).** `capability/_policy.py`. Drei **aktive** Regeln (D6 — nur was
erfuellbar ist):

| Regel | Aussage | Erlaubnisfall | Ablehnungs-/needs-Fall |
|---|---|---|---|
| `provenance` | SI-1/SI-2: `external-write` aus `derived` **hart verweigert**, aus `operator` autorisierungspflichtig | `derived` + sicheres `network-read` laeuft | `derived` + `external-write` → **deny** |
| `confirm-destructive` | SI-7: destruktiv nur nach echter Operator-Bestaetigung desselben Turns | `confirmed=True` → allow | `confirmed=False` → **needs** `CONFIRMATION` |
| `safe-target` | D7: `network-read` nur auf zulaessiges Ziel | `target_allowed=True` → allow | `False` → **deny**, `None` → **needs** (fail-closed) |

Fuenf weitere Regeln sind **benannt und datiert, aber nicht aktiv** (`presence-unlocked`,
`preview-transfer`, `budget`, `grant`, `connector-principal`) — mit einem Test, der genau
das festnagelt. `unknown` wird nirgends als "erlaubt" durchgewunken.

**Bewusste Praezisierung.** Fuer `network-read` fuegt Provenance ausdruecklich **nichts**
hinzu (Amendment 1 §A1.5 E4). Nach dem Buchstaben von §14 waere eine zusaetzliche
Anforderung denkbar gewesen — sie haette aber **jede Sprachsuche bestaetigungspflichtig**
gemacht und damit das beobachtbare Verhalten geaendert (§28.4). Ein Test haelt die
Richtung fest: `derived` darf nie eine Anforderung **entfernen**, die `operator` hat.

**Mutationsnachweis (ausgefuehrt).** Sieben Mutationen an `_policy.py`, je ein voller
Testlauf, Datei danach byte-identisch wiederhergestellt:

| Mutation | Ergebnis |
|---|---|
| `destructive` braucht keine Bestaetigung mehr | **ROT** |
| unbekanntes Ziel wird fail-**open** durchgewunken | **ROT** |
| blockiertes Ziel nur noch `needs` statt `deny` | **ROT** |
| `derived` + `external-write` nur noch `needs` statt `deny` | **ROT** |
| `deny` gewinnt nicht mehr ueber `needs` | **ROT** |
| `needs` akkumuliert nicht (Abbruch nach erster Regel) | **ROT** |
| Regelmenge geschrumpft (`safe-target` deaktiviert) | **ROT** |

**Reinheitsnachweis.** Subprozess mit Fallen auf `open`, `socket`, `getaddrinfo`,
`Popen`, `time.time`, `time.monotonic`, `time.perf_counter` und der ersetzten
`datetime.datetime`-Klasse: Import **und** alle `decide`-Kombinationen laufen sauber
durch (§28.1).

**Regression.** Suite **927** grün (vorher 903, +24). Sicherheitskritischer Block
(`test_capability_policy` + `test_capability_contract`, 57 Faelle) **5× flakefrei**.
Fixture `a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` — bytegleich.

**Commit.** Slice 1 war `e76ed4c`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** `capability/_policy.py` und die Testdatei entfernen, Exporte aus
`__init__.py` zuruecknehmen. Weiterhin **kein Produktionsaufrufer** — null Laufzeitwirkung.

**Offene Restrisiken.** `evidence.target_allowed` wird in diesem Slice vom Aufrufer
gesetzt; der tatsaechliche `TargetGuard` entsteht erst in Slice 6. Bis dahin ist die
`safe-target`-Regel korrekt, aber ohne Zulieferer — sie kann noch niemanden schuetzen.
Das ist der Grund, warum Slice 6 der eigentliche Sicherheitsnachweis ist und nicht dieser.

---

## Slice 3 — Coordinator ohne Produktionsaufrufer

**Ziel.** Den Lifecycle `validate -> preview -> authorize -> execute -> verify` bauen,
mit geschlossenem Ergebnismodell und den in Amendment 1 §A1.6 gezogenen Grenzen. Noch
immer ohne jeden Produktionsaufrufer.

**Oeffentlicher Seam.** `SEAM-CAPABILITY-COORDINATION` — `Coordinator.attempt`,
`.inspect`, `.health`, `.idempotency_key` sowie das `Outcome`-Modell. Kontrollierte
Grenze: **Fake-Vertraege** plus injizierte Clock und Audit-Senke. Kein Provider, kein
Netz, kein Dateisystem.

**Ausgangsverhalten.** Es gab keinen Lifecycle. Timeout lag als einziges
`asyncio.wait_for` in `assistant_core.py:324`; Cancel, Confirmation und Fehlerbehandlung
waren ueber `assistant_core` und den WS-Endpunkt verteilt; Teilerfolg war nicht
darstellbar.

**RED (tatsaechlich beobachtet).** `Ran 26 tests ... FAILED (errors=26)` mit
`AttributeError: module 'capability' has no attribute 'Coordinator'`.

**GREEN (minimal).** `capability/_coordinator.py` plus zwei neue Eintraege im
`obslog`-Katalog (`capability.attempted`, `capability.unverified`).

**Nicht-Ueberspringbarkeit — verhaltensbasiert belegt, nicht ueber eine Stufenliste.**
Was nicht laufen darf, hinterlaesst keine Spur: bei `deny` und bei `needs` bleibt die
Aufzeichnungsliste des Fake-Executors leer; ein Schemaverstoss wirft **auch dann**, wenn
die Policy ohnehin verweigert haette (damit ist `validate` vor `authorize` belegt).

**Die vier Grenzen aus Amendment 1 §A1.6, jede mit Test:**

| Grenze | Umsetzung | Belegt durch |
|---|---|---|
| **Ein** Timeout-Owner | `asyncio.wait_for` im Coordinator; Ergebnis `timeout`, keine Exception | `test_timeout_becomes_an_outcome_not_an_exception` |
| `CancelledError` unveraendert, **kein** Verify danach | eigener `except`-Zweig mit blossem `raise`; **kein** `finally` | `test_cancelled_error_propagates_unchanged`, `test_no_audit_and_no_verify_after_cancellation` |
| `cancelled` nur kooperativ | eigener Markertyp `capability.Cancelled` als Rueckgabewert des Executors | `test_cancelled_outcome_is_only_a_cooperative_domain_cancellation` |
| Key erzeugt und **uebergeben**, kein Cache | `AttemptContext.idempotency_key`; zwei identische Attempts fuehren **beide** aus | `test_identical_attempts_both_execute_there_is_no_cache` |

**Weitere strukturelle Zusagen.** `verify` stuft `ok` zu `partial` herab, nie umgekehrt;
`verify="none"` wird **vermerkt** (`capability.unverified`), statt Erfolg zu behaupten;
die Fehlermeldung verlaesst den Coordinator nie — nur der Typ (SI-9); Audit traegt
ausschliesslich Allowlist-Metadaten, und ein Test prueft, dass jeder verwendete
Eventname `obslog` tatsaechlich bekannt ist (sonst waere das Audit eine Behauptung ohne
Wirkung). Der Preview-Hash entsteht aus der **eingefrorenen** Eingabe — TOCTOU ist damit
nicht darstellbar statt nur unwahrscheinlich.

**Zwischenbefund (zweiter eigener Testfehler, systematisch geklaert).** Die Suite war im
Modul allein grün, im Verbund aber **reproduzierbar** (5/5) rot — also keine Flakiness.
Ursache: `_coordinator` importiert `asyncio`, das `ssl` laedt, und `ssl` fuehrt beim
Import `class SSLSocket(socket)` aus. Meine Sandbox hatte `socket.socket` durch eine
**Funktion** ersetzt, worauf schon die Klassendefinition scheiterte — die Probe sagte
also nichts ueber das gepruefte Modul aus. Dasselbe noch einmal bei
`asyncio.windows_utils` mit `class Popen(subprocess.Popen)`. Gegenmittel: die Fallen sind
jetzt **vererbbare Klassen**, deren `__init__` wirft. Der Import darf die Klasse
ableiten; jede tatsaechliche Benutzung fliegt auf.

**Gegenprobe zur entschaerften Sandbox (Pflicht, sonst waere sie vacuous).** Fuenf echte
Verstoesse in den Importpfad bzw. in `decide` eingebaut — **alle fuenf ROT**: Datei-I/O,
DNS, Socket-Verbindung, Subprozess, Uhrzugriff.

**Mutationsnachweis (ausgefuehrt).** Neun Mutationen an `_coordinator.py`, je ein voller
Testlauf, Datei danach byte-identisch wiederhergestellt:

| Mutation | Ergebnis |
|---|---|
| `deny` haelt `execute` nicht mehr auf | **ROT** |
| `needs` haelt `execute` nicht mehr auf | **ROT** |
| `CancelledError` wird zu einem Outcome verschluckt | **ROT** |
| `verify` stuft `partial` zu `ok` **hoch** | **ROT** |
| Timeout wirft statt Outcome | **ROT** |
| `verify="none"` behauptet Erfolg ohne Vermerk | **ROT** |
| Audit traegt die Eingabe mit | **ROT** |
| Fehlermeldung leckt in das Outcome | **ROT** |
| Retry-Schleife eingebaut | **ROT** |

**Regression.** Suite **953** grün (vorher 927, +26). Cancellation- und Sicherheitsblock
(83 Faelle) **5× flakefrei**. Fixture `a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` —
bytegleich.

**Commit.** Slice 2 war `2ff027b`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** `capability/_coordinator.py` und die Testdatei entfernen, Exporte und
die zwei `obslog`-Katalogeintraege zuruecknehmen. Weiterhin **kein Produktionsaufrufer**
— null Laufzeitwirkung.

**Offene Restrisiken.** Eine propagierte `CancelledError` wird **nicht auditiert**: jede
Arbeit in diesem Pfad koennte den Abbruch verzoegern, und ein eigener Ausgang wuerde ihn
mit der kooperativen Stornierung verwechseln. Das ist eine bewusste, hier benannte
Beobachtungsluecke — kein Versehen.

---

## Slice 4 — Runtime Ownership und Injection

**Ziel.** Die Runtime besitzt Registry, Regeln und **genau einen** Coordinator; die
Konstruktion bleibt import- und I/O-frei. Ein runtime-gebundener Capability-Hook wird
ueber `server/_run_turn` in `assistant_core` injiziert — ohne Rueckreferenz von
`assistant_core` auf `server` oder eine globale Runtime.

**Oeffentlicher Seam.** `capability.Coordinator` als `Runtime.capabilities`;
`capability.build_registry`/`CapabilityDeps`/`pilot_contracts`; die um `capabilities`
erweiterte Signatur von `assistant_core.process_message`/`run_action_and_respond`.

**Ausgangsverhalten.** Der Coordinator existierte (Slice 3), war aber nirgends verdrahtet.
`assistant_core.process_message` kannte keinen Capability-Pfad; die Runtime besass keinen
Kernel.

**RED (tatsaechlich beobachtet).** `Ran 11 tests ... FAILED (failures=4, errors=3)` mit
`AttributeError: 'Runtime' object has no attribute 'capabilities'`.

**GREEN (minimal).**
* `capability/_pilots.py` — `CapabilityDeps` (frozen; **kein Service Locator**: eine
  konkrete Objektreferenz auf die Runtime, kein globaler String-Lookup) und
  `build_registry`/`pilot_contracts`. In dieser Phase ist die Pilot-Liste leer; sie
  waechst Slice fuer Slice (5/7/8/9).
* `runtime.py` — genau ein `self.capabilities = capability.Coordinator(...)`, I/O-frei
  konstruiert, Dedupe-Scope an den `session_token` gebunden (§19).
* `assistant_core.py` — `process_message`/`run_action_and_respond` nehmen ein optionales
  `capabilities` an und reichen es durch; **kein** `import server`, **kein** Modul-Global
  `runtime`.
* `server.py` — `_run_turn` injiziert `capabilities=rt.capabilities` (Injektionspunkt wie
  beim bestehenden `_launcher_hook(rt)`).

**Zwischenbefund (eigener vacuous Test, systematisch geklaert).** Der Mutationslauf zeigte
den ersten `dedupe_scope`-Test als **grün trotz Mutation** — er baute eigene
Coordinatoren, statt `rt.capabilities` zu pruefen, und sagte damit nichts ueber die
Runtime-Bindung aus. Korrigiert: der Test speist jetzt ueber den oeffentlichen Builder
`pilot_contracts` einen Probe-Vertrag ein und vergleicht die Keys der **tatsaechlich vom
Runtime gebauten** Coordinatoren zweier Runtimes mit verschiedenen Tokens.

**Zwischenbefund (Regression in Alt-Test-Doubles, korrekt behoben).** Die volle Suite
brach mit 5 Failures + 1 Error: fuenf implementation-coupled Alt-Test-Doubles
(`test_confirm_flow` `fake_run`, `test_ws` `slow_process`/`proc` ×4, `test_logging_privacy`
`fake_process`) spiegelten die um `capabilities` erweiterte Signatur nicht und warfen
`TypeError: unexpected keyword argument 'capabilities'`. Ein Test-Double **muss** die reale
Schnittstelle nachbilden — die Signaturen wurden um `capabilities=None` ergaenzt. **Kein**
Verhalten wurde gelockert, kein Test uebersprungen; die Doubles pruefen weiterhin genau
dasselbe.

**Mutationsnachweis (ausgefuehrt).** Drei Verdrahtungsmutationen, je ein Testlauf, Dateien
danach byte-identisch:

| Mutation | Ergebnis |
|---|---|
| Hook nicht an `run_action_and_respond` durchgereicht | **ROT** |
| `_run_turn` injiziert `capabilities=None` statt `rt.capabilities` | **ROT** |
| Dedupe-Scope nicht an `session_token` gebunden | **ROT** (nach Testkorrektur) |

**Regression.** Suite **964** grün (vorher 953, +11). Smoke **Exit 0** (Produktionscode
beruehrt → Smoke gehoert dazu). Fixture `a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` —
bytegleich.

**Commit.** Slice 3 war `76d812f`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** Commit reverten: `capability/_pilots.py` entfaellt, die drei
Produktionsdateien (`runtime`/`assistant_core`/`server`) kehren auf die vorherige Signatur
zurueck, die Test-Doubles ebenfalls. Der `capabilities`-Parameter ist optional
(Default `None`) — der Rueckbau kann keinen bestehenden Aufrufer brechen.

**Offene Restrisiken.** Der Hook ist verdrahtet, aber in dieser Phase **dormant**: die
leere Pilot-Registry bedeutet, dass `run_action_and_respond` das `capabilities`-Objekt
noch nicht nutzt. Der erste tatsaechliche Dispatch kommt mit Slice 5 (`web.search`). Bis
dahin ist die Verdrahtung belegt, aber ohne Wirkung auf einen Produktionspfad — genau die
Grenze, die dieser Slice zieht.

---

## Slice 5 — Pilot web.search

**Ziel.** `[ACTION:SEARCH]` byte- und shape-exakt lassen, aber `web.search` ueber
**denselben** Coordinator fuehren. Der Legacy-Adapter setzt Provenance `derived`; das rohe
Ergebnis wird byte-identisch in die bestehende Action-/Summary-/TTS-Orchestrierung
projiziert.

**Oeffentlicher Seam.** `SEAM-CAPABILITY` (web.search im Zensus) + `SEAM-CAPABILITY-COORDINATION`
(Dispatch). `capability.is_migrated`, `capability.run_migrated`, `capability.MIGRATED_ACTIONS`.
Kontrollierte Grenze: `browser_tools.search_and_read` (Provider) — nie echtes Netz.

**Ausgangsverhalten.** `SEARCH` lief ueber `run_action_and_respond` ->
`asyncio.wait_for(execute_action(...), spec.timeout)` -> `actions._exec_search` ->
`browser_tools.search_and_read`. Kein Vertrag, keine Provenance, kein Kernel.

**RED (tatsaechlich beobachtet).** `Ran 9 tests ... FAILED (failures=1, errors=7)` mit
`AssertionError: 'web.search' not found in <Registry ...>`.

**GREEN (minimal).**
* `capability/_legacy.py` — `web.search`-Vertrag (Version 1), `is_migrated`,
  `run_migrated`. `execute` importiert `browser_tools` **lazy** und formatiert das
  Ergebnis deckungsgleich mit `actions._exec_search`.
* `capability/_pilots.py` — `web.search` in `pilot_contracts`.
* `assistant_core.run_action_and_respond` — dispatcht `SEARCH` bei vorhandenem
  `capabilities` ueber `capability.run_migrated`; alle anderen Actions unveraendert ueber
  `execute_action`. **Nur genau ein Timeout-Owner**: der migrierte Pfad hat **kein** aeusseres
  `asyncio.wait_for`, weil der Coordinator den Timeout traegt (Amendment 1 §A1.6 F1).

**Vollstaendige Effekt-Deklaration (Amendment 1 §A1.2).** `web.search.effects =
{network-read, local-execute}`: network-read fuer Suche + Summary-LLM + TTS, local-execute
fuer den sichtbaren Chromium-Prozess und den PowerShell-`SetForegroundWindow`-Fokus.
Damit ist der Vertrag `GOVERNED` — die Folgewirkungen laufen nicht mehr unsichtbar an einer
Ausfuehrungsfunktion vorbei.

**Byte-Identitaet belegt.** Ein Test faehrt dieselbe gefakte Suchantwort durch den
Alt-Pfad (`actions._exec_search`) **und** den migrierten Pfad und vergleicht das rohe
Ergebnis — identisch. Damit bleiben Summary-LLM-Eingabe und gesprochene Frames unveraendert.

**Mutationsnachweis (ausgefuehrt).** Fuenf Mutationen, alle **ROT**:

| Mutation | Ergebnis |
|---|---|
| Provenance `operator` statt `derived` | **ROT** |
| Zensus: `local-execute` weggelassen (Unter-Deklaration) | **ROT** |
| Ergebnis nicht mehr byte-identisch (`[:2000]`→`[:1000]`) | **ROT** |
| `SEARCH` nicht mehr als migriert markiert | **ROT** |
| Dispatch entfernt (`SEARCH` zurueck auf `execute_action`) | **ROT** |

**Regression.** Suite **973** grün (vorher 964, +9). Smoke **Exit 0**. Fixture
`a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` — bytegleich.

**Commit.** Slice 4 war `366046a`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** Commit reverten: `web.search` faellt aus `pilot_contracts`, der Dispatch
in `run_action_and_respond` entfaellt, `SEARCH` laeuft wieder ueber `execute_action`. Der
Alt-Pfad (`_exec_search`) blieb die ganze Zeit unangetastet daneben — reiner Rueckbau ohne
Datenmigration.

**Offene Restrisiken (ehrlich).** In diesem Slice ist die `safe-target`-Evidenz von
`web.search` fest auf `True` gesetzt: sie spiegelt den **festen** Suchmaschinen-Host, nicht
den geklickten Ergebnis-Link. **Die SSRF-Durchsetzung auf jede tatsaechliche Navigation
(Ergebnis-Klick, Redirect) ist Slice 6** und hier noch nicht vorhanden. Slice 5 behauptet
**keine** TM-002-Mitigation.

---

## Slice 6 — SSRF TargetGuard und beide Transportfamilien

**Ziel.** Ein gemeinsamer **reiner** `TargetGuard`, erzwungen durch **zwei**
Produktionsadapter (httpx **und** Playwright), der die tatsaechlich aufgeloeste Adresse
gegen eine Denylist prueft — vor jedem Request und jedem Redirect-/Navigations-Hop
(D7, Amendment 1 §A1.3).

**Oeffentlicher Seam.** `SSRF-Transport/TargetGuard` — `capability.TargetGuard`
(`check_url`/`check_ip`/`ensure`), `capability.httpx_guarded_get`,
`capability.install_page_guard`, `capability.guarded_goto`, `capability.SSRFBlocked`.
Kontrollierte Grenze: **injizierter Resolver** + Transport-/Playwright-Doubles —
**niemals echtes Internet**.

**Playwright-Seam belegbar (kein Blocker).** Vorab geprueft: `Page.route`, `Page.goto`,
`Response.server_addr`, `Route.abort`, `Route.continue_`, `Request.url` existieren alle
in der installierten Playwright-Version. Damit ist der produktive Hauptpfad
nachweisbar schuetzbar — die Abbruchbedingung `PROMPT 19 BLOCKIERT – PLAYWRIGHT-SSRF-SEAM
NICHT BELEGBAR` trifft **nicht** zu.

**Ausgangsverhalten.** `actions.normalize_url` prueft nur das Schema; der Host wurde nie
geprueft. Beide httpx-Fallbacks nutzten `follow_redirects=True` ohne Revalidierung; jede
`page.goto` navigierte ungeprueft. TM-002 war vollstaendig offen (RFC-0007 §2.5).

**RED (tatsaechlich beobachtet).** `Ran 27 tests ... FAILED (errors=30)` mit
`AttributeError: module 'capability' has no attribute 'TargetGuard'`.

**GREEN (minimal).**
* `capability/_ssrf.py` — reiner `TargetGuard` (nur der DNS-Resolver ist die eine
  injizierte Grenze), die httpx-Redirect-Schleife und die Playwright-Adapter.
* `browser_tools.py` — **jede** `page.goto` laeuft ueber `_guarded_goto`
  (Route-Guard installieren + Vorab-Pruefung + verbundene-IP-Nachpruefung); beide
  httpx-Fallbacks nutzen `follow_redirects=False` mit gepruefter Kette. Fail-closed:
  ist kein Guard konfiguriert, wird ein strikter Default-Guard erzeugt.
* `runtime.py` — genau **ein** Guard, den Coordinator-Deps und `browser_tools`
  (`configure_guard`) teilen.

**Denylist (§21), je Kategorie erlaubend UND verweigernd getestet.** Loopback (v4/v6),
RFC1918, Link-local (v4/v6), IPv6-ULA, Cloud-Metadata, ipv4-mapped Loopback,
Jarvis-Selbstzugriff `127.0.0.1:8340`. Dazu: Literal-IP, localhost, **gemischte
DNS-Antworten** (ein privater Record verwirft das ganze Ziel), Userinfo, ungueltige
Ports, fehlende Hosts, nicht-http-Schemata, erlaubte oeffentliche Ziele.

**Verdrahtungsbeleg.** Zwei Tests fahren den **produktiven** browser_tools-Pfad
(`_search_links_fallback`, `fetch_page_text_fallback`) mit einem Guard, dessen Resolver
auf Loopback/privat zeigt — beide liefern leer/Fehler. Damit ist belegt, dass die
Produktion den Guard wirklich aufruft, nicht nur der Guard fuer sich.

**Mutationsnachweis (ausgefuehrt, 12 Mutationen).** Neun **ROT**, drei **GRUEN** —
letztere **untersucht und als bewusste Redundanz belegt**, nicht als Testluecke:

| Mutation | Ergebnis |
|---|---|
| privates Netz nicht mehr blockiert (**tragende Pruefung**) | **ROT** |
| Userinfo nicht mehr abgelehnt | **ROT** |
| Nur-http-Schema-Pruefung entfernt | **ROT** |
| gemischte DNS-Antwort: nur erste IP geprueft | **ROT** |
| httpx: Redirect-Hop nicht mehr geprueft | **ROT** |
| httpx: Redirect-Kette unbegrenzt | **ROT** |
| Playwright: verbundene IP nicht mehr geprueft | **ROT** |
| Playwright: Route-Handler bricht `denied` nicht ab | **ROT** |
| Playwright: keine Vorab-Navigationspruefung | **ROT** |
| Loopback-Zweig entfernt | GRUEN — Redundanz |
| Link-local-Zweig entfernt | GRUEN — Redundanz |
| ipv4-mapped-Entpackung entfernt | GRUEN — Redundanz |

**Warum die drei GRUEN korrekt sind (empirisch belegt).** In CPython 3.14 ist
`ipaddress.is_private` ein **Catch-all**, das Loopback, Link-local und ipv4-mapped
bereits einschliesst (`127.0.0.1`, `169.254.10.20`, `::ffff:127.0.0.1` sind alle
`is_private=True`). Entfernt man **einen** spezifischen Zweig, bleibt das Ziel durch
`is_private` weiter blockiert — das Verhalten (deny) aendert sich nicht. Die tragende
Pruefung (`is_private`) ist mit dem RFC1918-Fall **scharf** getestet (Mutation ROT). Die
expliziten Zweige sind **Defense-in-Depth**: sie machen die Absicht lesbar und halten den
Schutz, falls sich die `ipaddress`-Semantik je aendert. (Praezedenz: RFC-0006 Szenario 14
— redundante Guards ehrlich dokumentiert.)

**Bereinigung.** Der urspruengliche `self_port`-Zweig war **unerreichbar** (der
`is_loopback`-Zweig kehrt vorher zurueck) und wurde entfernt; der Selbstzugriff ist in
der Loopback-Denial-Meldung ausdruecklich benannt.

**Regression.** Suite **1002** grün (vorher 973, +29). SSRF-Block (48 Faelle) **5×
flakefrei**. Smoke **Exit 0**. Fixture `a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` —
bytegleich.

**Commit.** Slice 5 war `8087d0c`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** Commit reverten: `browser_tools` kehrt auf `follow_redirects=True` und
ungeprueftes `page.goto` zurueck; `capability/_ssrf.py` und die Runtime-Injektion
entfallen. Kein Datenformat betroffen.

**Offene Restrisiken (ehrlich).** **TM-002 ist nur teilweise mitigiert.** Die
Pro-Verbindungs- und Pro-Hop-Pruefung erschwert SSRF erheblich, aber **ohne IP-Pinning**
wird nicht behauptet, die tatsaechlich verbundene IP kryptografisch zu binden.
**DNS-Rebinding bleibt Restrisiko** (D7/R7, Phase 9). Der Route-Handler und die
`server_addr`-Nachpruefung verkleinern das Fenster, schliessen es aber nicht.

---

## Slice 7 — Pilot memory.forget

**Ziel.** `MEMORY_FORGET` ueber den Coordinator fuehren, ohne dass sich der gesprochene
Confirmation-Pfad aendert. Erster Attempt ergibt `needs:confirmation`; das gesprochene
„Ja" fuehrt denselben pending Attempt aus. **Kein** Grant, **kein** neuer Session-Zustand,
**keine** neue Wire-Form. `memory.forget` bleibt Confirmation, wird nicht umetikettiert
(§16).

**Oeffentlicher Seam.** `SEAM-CAPABILITY` (memory.forget-Zensus), `SEAM-POLICY`
(Confirm-Regel), `SEAM-CAPABILITY-COORDINATION` (Dispatch mit `confirmed`).
Kontrollierte Grenze: `memory.forget_memory` (Vault) — nie echter Vault.

**Ausgangsverhalten.** `MEMORY_FORGET` (einzige `risk="confirm"`-Action) → process_message
`request_confirmation` → gesprochene Rueckfrage → „Ja" → `run_action_and_respond` →
`execute_action` → `memory.forget_memory`.

**RED (tatsaechlich beobachtet).** `Ran 9 tests ... FAILED (failures=3, errors=6)` mit
`AssertionError: None != 'MEMORY_FORGET'` (memory.forget nicht in der Registry, Dispatch
reicht `confirmed` nicht durch).

**GREEN (minimal).**
* `capability/_legacy.py` — `memory.forget`-Vertrag (Version 1), `run_migrated` um
  `confirmed` erweitert. `execute` deckt sich mit `actions._exec_memory_forget`.
* `assistant_core.run_action_and_respond` nimmt `confirmed` und reicht es an
  `run_migrated`; **`process_message` setzt `confirmed=True` genau im „Ja"-Zweig** — das
  gesprochene „Ja" IST die echte Operator-Bestaetigung desselben offenen Turns.

**Confirmation bleibt Confirmation (§16).** Der `memory.forget`-Vertrag traegt
`effects={destructive, network-read}`; die Policy verlangt `CONFIRMATION`, **nie**
`AUTHORIZATION` — ein Test nagelt das fest. Voice erfuellt nie einen Grant (SI-2); das
beobachtbare Verhalten ist exakt das heutige.

**„Modellinhalt kann sich nie selbst bestaetigen" — belegt.** `confirmed` kommt
ausschliesslich aus dem `process_message`-„Ja"-Zweig (Operator-Utterance, durch
`is_confirmation` validiert), nie aus dem `[ACTION:…]` (Provenance `derived`). Test: erster
Attempt mit `confirmed=False` → `needs:confirmation`, **der Vault wird nicht angefasst**.

**Byte-Identitaet belegt.** Dieselbe gefakte `forget_memory`-Antwort durch Alt- und
migrierten Pfad → identisches rohes Ergebnis → Summary-LLM-Eingabe und Frames unveraendert.

**CancelledError erhalten.** Wirft die Loeschung `CancelledError`, reicht der Coordinator
sie unveraendert durch (Test).

**Zwischenbefund (zwei Alt-Test-Doubles, korrekt angeglichen).** Wie in Slice 4/5 spiegelten
zwei Doubles die um `confirmed` erweiterte Signatur nicht (`test_confirm_flow` `fake_run`,
mein eigener `run_migrated`-Spy im Search-Test). Beide um `confirmed=False` ergaenzt — kein
Verhalten gelockert.

**Mutationsnachweis (ausgefuehrt).** Vier Mutationen, alle **ROT**:

| Mutation | Ergebnis |
|---|---|
| Zensus: `destructive` weggelassen (Unter-Deklaration) | **ROT** |
| `confirmed` immer `True` → Selbstbestaetigung moeglich | **ROT** |
| `MEMORY_FORGET` nicht mehr migriert | **ROT** |
| „Ja" reicht `confirmed` nicht mehr durch | **ROT** |

**Regression.** Suite **1011** grün (vorher 1002, +9). Confirm-/Cancellation-Block **5×
flakefrei**. Smoke **Exit 0**. Fixture `a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` —
bytegleich.

**Commit.** Slice 6 war `3edd6ec`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** Commit reverten: `memory.forget` faellt aus `pilot_contracts`/
`MIGRATED_ACTIONS`, der `confirmed`-Parameter entfaellt (optional, Default `False` — bricht
keinen Aufrufer). `MEMORY_FORGET` laeuft wieder ueber `execute_action`; der gesprochene
Confirm-Pfad war die ganze Zeit unveraendert.

**Offene Restrisiken.** Keine neuen. `launcher.profile.delete` bleibt die dokumentierte
destructive Luecke ohne serverseitig belegbare Bestaetigung (Amendment 1 §A1.4) — das
loest erst ein Preview-/Grant-Vertrag in Phase 10.

---

## Slice 8 — REST-Pilot launcher.profile.rename

**Ziel.** Die Rename-Route ueber **denselben** Coordinator fuehren (Provenance `operator`),
ohne dass sich Statuscode, Response-Body, Broadcast oder Legacy/V1-Vertrag aendern.
Configuration bleibt der einzige Writer; **keine** direkte Mutationsumgehung. Amendment 1
§A1.4 ersetzt damit `launcher.profile.delete` als REST-Pilot — gleiche Adapterform, aber
`local-write` statt `destructive`.

**Oeffentlicher Seam.** `SEAM-CAPABILITY-COORDINATION` (REST-Adapter), `SEAM-REST`
(Vertrag unveraendert). Seam-Setup wie `test_launcher_api`: eigene Runtime + Temp-Config +
lifespan-fahrender TestClient.

**Ausgangsverhalten.** `POST /launcher/profiles/{id}/rename` rief direkt
`_persist_launcher(rt, RenameProfile(...), "profile", corr)`.

**RED (tatsaechlich beobachtet).** `Ran 7 tests ... FAILED (failures=2, errors=1)` mit
`AssertionError: None is not <Provenance.OPERATOR>` (Capability nicht in der Registry, Route
dispatcht nicht ueber den Coordinator).

**GREEN (minimal).**
* `capability/_coordinator.py` — `attempt(..., *, meta=None)` und
  `AttemptContext.meta`: **opake Transport-Metadaten** (die Wire-Correlation fuer den
  Broadcast). Sie gehen **nicht** in Validierung oder Idempotency Key ein — `correlation_id`
  ist keine Job-ID, `event_id` kein Idempotency Key (§18/§19).
* `runtime.py` — `configure_launcher_persist`/`persist_launcher`: explizite
  Instanz-Injektion der Server-Orchestrierung (kein Modul-Global, kein Service Locator, kein
  `capability`→`server`-Import). Ohne Injektion **fail-closed** (Fehler statt Umgehung).
* `server.py` — `create_app` injiziert `persist_launcher_intent`; die Rename-Route
  dispatcht ueber `rt.capabilities.attempt(...)` mit `Provenance.OPERATOR`.
* `capability/_legacy.py` — `launcher.profile.rename`-Vertrag (Version 1); `execute`
  persistiert ausschliesslich ueber `runtime.persist_launcher` (Configuration = einziger
  Writer) und zieht die Correlation aus `ctx.meta`.

**Vertragserhalt belegt.** Erfolg → 200 + `_profiles_response()`; unbekanntes Profil → 404;
kein Token → 403; die Temp-Datei traegt den neuen Namen (Configuration schrieb). Der
bestehende `test_launcher_api.test_rename_profile` und die RFC-0005-Wire-/Broadcast-Tests
bleiben grün — Status/Body/Broadcast unveraendert.

**Delete bleibt die offene Luecke.** Ein Test belegt: `DELETE /launcher/profiles/{id}`
laeuft **nicht** ueber den Coordinator, loescht aber weiterhin (Verhalten unveraendert).
`launcher.profile.delete` bleibt die dokumentierte destructive Luecke ohne serverseitig
belegbare Bestaetigung (Amendment 1 §A1.4) — direkter DELETE wird **nicht** zu „Confirmation"
umetikettiert.

**Zwischenbefund (vorbestehende Test-Isolationsluecke, aufgedeckt).** Die volle Suite brach
mit 5+6 Fehlern in `test_dashboard_api` und `test_conversation_ws` (403). Ursache
**systematisch geklaert**: der Lifespan setzt per RFC-0002-A3-Kompat-Alias
`server.SESSION_TOKEN = rt.session_token` (`server.py:889`). Jeder lifespan-fahrende Test
mit eigener Runtime setzt damit das Modul-Token um — bisher latent, weil **alle** solchen
Tests (launcher/music/settings) alphabetisch **nach** dashboard sortieren. Mein neuer Test
(`capability…`) sortiert **davor** und deckt die Pollution auf; `test_launcher_api` **vor**
`test_dashboard_api` bricht identisch (belegt: pre-existing, nicht meine Logik). In
Produktion (genau eine Runtime) ist die Zuweisung korrekt — es ist rein Test-Isolation.
**Fix:** mein Test sichert `server.SESSION_TOKEN` in `setUp` und stellt es in `tearDown`
wieder her. Kein Produktionscode geaendert, kein Test gelockert.

**Mutationsnachweis (ausgefuehrt).** Vier Mutationen, alle **ROT**:

| Mutation | Ergebnis |
|---|---|
| Zensus: `local-write` weggelassen | **ROT** |
| `execute` umgeht `persist_launcher` (direkter Bypass) | **ROT** |
| Route dispatcht **nicht** ueber den Coordinator | **ROT** |
| Provenance `derived` statt `operator` | **ROT** |

**Regression.** Suite **1018** grün (vorher 1011, +7). Smoke **Exit 0**. Fixture
`a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` — bytegleich.

**Commit.** Slice 7 war `bdee9db`; die SHA dieses Slices traegt der Folge-Slice nach.

**Rueckrollweg.** Commit reverten: die Route ruft wieder `_persist_launcher` direkt; die
Runtime-Persist-Methode, die `meta`-Erweiterung und der Vertrag entfallen. Der Alt-Pfad war
die ganze Zeit unveraendert erreichbar.

**Offene Restrisiken.** `launcher.profile.delete` bleibt ungeschuetzt (Amendment 1 §A1.4) —
erst ein serverseitig nachweisbarer Preview-/Grant-Vertrag (Phase 10) schliesst sie.

---

## Slice 9 — Pilot context.refresh

**Ziel.** Startup **und** Post-Settings-Save laufen ueber **dieselbe** Capability. Die
bestehende Lifespan-, Commit- und Degraded-Semantik bleibt erhalten; Wetterzugriff und
Vault-Scan sind vollstaendig deklariert. Kein Config-File, kein Vault, kein Netz in Tests;
keine zusaetzlichen Startup-Aufrufe oder Providerkosten.

**Oeffentlicher Seam.** `SEAM-CAPABILITY-COORDINATION` — `runtime.refresh_context`,
`capability.context.refresh`. Kontrollierte Grenze: `assistant_core.refresh_data`
(wttr.in + Vault) — im Test ein No-Op.

**Ausgangsverhalten.** Zwei Nicht-Nutzer-Ausloeser riefen direkt
`asyncio.to_thread(assistant_core.refresh_data)`: `runtime.aopen` (Serverstart,
fire-and-forget-Task) und `server._post_commit` (nach jedem Settings-Save, mit
Degraded-Behandlung).

**RED (tatsaechlich beobachtet).** `Ran 6 tests ... FAILED (failures=2, errors=3)` mit
`AssertionError: False is not true` (context.refresh nicht in der Registry; kein
Capability-Dispatch).

**GREEN (minimal).**
* `capability/_legacy.py` — `context.refresh`-Vertrag (Version 1), leere Ein-/Ausgabe;
  `execute` = `await asyncio.to_thread(assistant_core.refresh_data)`. Vollstaendig
  deklariert: `effects={network-read, read-sensitive}` (wttr.in + Vault-Scan, §2.6.3).
  Provenance `operator` (systeminitiiert, nicht aus untrusted Inhalt).
* `runtime.py` — `refresh_context()` dispatcht ueber den Coordinator; `aopen` startet den
  Task damit (weiterhin fire-and-forget: ein Fehler wird `FAILED`, crasht den Startup
  nicht). **Kein zusaetzlicher Aufruf** — derselbe eine Refresh.
* `server._post_commit` — nutzt `rt.refresh_context()`; ein nicht erfolgreicher Ausgang
  rollt die persistierte Configuration NIE zurueck, sondern erzeugt den
  **Degraded**-Zustand (Semantik unveraendert, inkl. `context.refresh_failed`-Log).

**Semantik-Erhalt belegt.** Ein Test faehrt den echten Lifespan-Startup und weist nach,
dass `refresh_data` **genau einmal** ueber die Capability laeuft (keine Extra-Kosten). Ein
zweiter Test setzt `refresh_data` nach dem Startup auf Fehler und weist nach, dass
`POST /settings` weiterhin **200 + `degraded`** liefert (Configuration bleibt gespeichert).

**Mutationsnachweis (ausgefuehrt).** Drei Mutationen, alle **ROT**:

| Mutation | Ergebnis |
|---|---|
| Zensus: `read-sensitive` weggelassen | **ROT** |
| Startup-Refresh umgeht die Capability (Alt-Pfad) | **ROT** |
| Post-Commit umgeht die Capability (direkter `refresh_data`) | **ROT** |

**Regression.** Suite **1024** grün (vorher 1018, +6). Smoke **Exit 0**. Fixture
`a58ca03c0dc2a877b5bd3ce336faa0cc4456dafb` — bytegleich.

**Commit.** Slice 8 war `9dc52da`; die SHA dieses Slices traegt der Abschluss-Slice nach.

**Rueckrollweg.** Commit reverten: `aopen` und `_post_commit` rufen wieder direkt
`asyncio.to_thread(assistant_core.refresh_data)`; `refresh_context`, der Vertrag und der
Registry-Eintrag entfallen. Kein Datenformat betroffen.

**Offene Restrisiken.** Keine neuen. Damit sind **vier** Produktionspfade migriert
(`web.search`, `memory.forget`, `launcher.profile.rename`, `context.refresh`); die
verbleibenden **20** Actions und **neun** REST-Routen folgen erst in Prompt 20
(Amendment 1 §A1.1). **Phase 5 ist mit diesem Prompt nicht abgeschlossen.**

---

## Slice 10 — Dokumentation, CI und Abschluss

**Ziel.** Doku, CI und die ehrliche Bilanz der Pilotphase.

**Geändert.**
* `.github/workflows/pr.yml` — `capability` im **Gate 1 (Syntax/Import, `compileall`)**.
  Die neuen Contract-/Policy-/Coordinator-/SSRF-Tests laufen im bestehenden
  Full-Suite-Gate (`unittest discover`) — es sind Unit-/Integrationstests, keine
  Browser-E2E.
* `docs/quality/TEST_SEAMS.md` — `SEAM-CAPABILITY`, `SEAM-POLICY`,
  `SEAM-CAPABILITY-COORDINATION`, `SSRF-Transport` **von `proposed` auf `approved`**
  (jetzt mit grüner Evidenz, Amendment 1 §A1.7 G4), inkl. Pilotgrenze.
* `docs/system/CURRENT_STATE.md` — Phase-5B-Statusblock (vier Piloten, drei aktive
  Regeln, SSRF, ehrliche Grenzen).
* `docs/system/CAPABILITY_MATRIX.md` — Hinweis, dass die Taxonomie jetzt für die vier
  Piloten in der Laufzeit existiert, die 20 Actions/9 Routen aber weiter nur `risk` tragen.
* `docs/security/RISK_REGISTER.md` — TM-001/TM-002 als **mitigation-in-progress
  (teilweise)** — ausdrücklich **nicht** „mitigated"; DNS-Rebinding datiert.
* `docs/architecture/RFC-0007-…` — Amendment 1 (Slice 0) und dieser Verlauf.

**Ehrliche Bilanz (Pflicht, Amendment 1 §A1.1).**

| Punkt | Stand nach Prompt 19 |
|---|---|
| Migrierte Produktionspfade | **4** — `web.search`, `memory.forget`, `launcher.profile.rename`, `context.refresh` |
| Verbleibende Actions | **20** (unmigriert, weiter nur `ActionSpec.risk`) |
| Verbleibende REST-Routen | **9** (unmigriert) |
| `launcher.profile.delete` | **offen** — kein serverseitig belegbarer Bestätigungsvertrag (Phase 10) |
| Gespeichertes `ActionSpec.risk` | **bleibt** — fällt erst bei 22/22 (Prompt 20, D10) |
| TM-001 (Prompt-Injection) | **nur teilweise** — SI-1 zentral durchsetzbar, aber nur 4 Pfade |
| TM-002 (SSRF) | **nur teilweise mitigiert** — Pro-Hop/Pro-Verbindung, **ohne IP-Pinning** |
| DNS-Rebinding / IP-Pinning | **offenes Restrisiko** (Phase 9) |
| Phase 5 | **NICHT abgeschlossen** (Rest in Prompt 20) |

**Regression.** Volle lokale Gates am finalen Branch-Stand (siehe Abschlussbericht des
Prompts). Keine Visual-Baseline aktualisiert; RFC-0005/RFC-0006 und Legacy byte-/
shape-unverändert.

**Commit.** Slice 9 war `3d46264`; die SHA dieses Slices und der finale Branch-Head
stehen im Abschlussbericht.
