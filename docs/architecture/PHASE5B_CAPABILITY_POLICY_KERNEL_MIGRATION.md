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
