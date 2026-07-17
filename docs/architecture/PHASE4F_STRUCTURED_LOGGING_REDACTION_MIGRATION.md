# Phase 4F — Strukturierte Betriebslogs und zentrale Redaction (Umsetzung von RFC-0004)

> Stand 2026-07-17. Umsetzung von
> [RFC-0004](RFC-0004-structured-operational-logging-redaction.md)
> (`Accepted for incremental implementation`, Variante C — Hybrid). Basis:
> `origin/master` `41a3e63`.

## Ausgangszustand

`logging.basicConfig` wurde beim **Import** von `server.py` ausgeführt (verletzt die
Import-Sicherheit aus RFC-0002), und über den ganzen Code verstreute
`logger.info/debug/warning`-Aufrufe mit roher `%`-Interpolation gaben private Inhalte in
die Logs. Sechs Leckvektoren waren mit synthetischen Sentinels belegt (RFC-0004 §5):

| # | Vektor | vorher |
|---|---|---|
| **L1** | Volle Such-/Besuchs-URL auf INFO | `browser_tools` loggte die komplette URL inkl. Query (= Suchbegriff) |
| **L2** | Clipboard-Inhalt | `assistant_core` „Action-Ergebnis" auf DEBUG |
| **L3** | Vault-Inhalt | dito („Action-Ergebnis") |
| **L4** | Roher Nutzer-Text | `server.py` `logger.debug("You: %s", …)` |
| **L5** | Exception-Message | `logger.*(exc_info=True)` mit Sentinel-Message |
| **L6** | Roher Traceback | dito (Traceback im `jarvis-launcher.log`) |

Diese Logs persistieren im rotierenden `jarvis-launcher.log` (stdout/stderr-Erfassung).

## Umgesetzte Slices, Commits und Rückrollpunkte

| Slice | Commit | Inhalt | Rückrollpunkt |
|---|---|---|---|
| **0+1** | `37ec787` | Modul `obslog`: `event`/`configure`/`reset`, geschlossener Eventkatalog, fail-closed Redaction (`_as_int/_as_bool/_as_id/_as_host`), datenfreier Fallback, importsicher; Contract-Tests am Sink-Output | Commit reverten; nichts Produktives war verdrahtet |
| **2** | `24a97ee` | Ownership: `basicConfig` aus dem Import raus; `_configure_logging` am Startpfad (beide Entry Points); `JARVIS_LOG_FORMAT`; In-Memory-Sink für Tests; Import-Sicherheit im Subprozess belegt | Commit reverten → `basicConfig` zurück |
| **3** | `fa421b1` | Höchstes Risiko: `server.py`, `assistant_core.py`, `actions.py` migriert (behebt **L2–L6**); Startup-Warnungen (mit lokalem Pfad) nur noch als Anzahl | Commit reverten |
| **4** | `f99d411` | Externe Grenzen: `browser_tools` (behebt **L1**), `tts`, `memory`, `clipboard_tools`, `app_launcher`, `monitors` | Commit reverten |
| **5** | `bd638e1` | `install_protection()`: zentrales, sanitierendes Schutznetz am Root-Handler (uvicorn/httpx/anthropic/playwright): URL→Host, Query-Secrets/Token→`<redacted>`, kein Traceback | Commit reverten → nur Allowlist-Events (kein Netz) |
| **6** | `c58f8e8` | Fault-Injection (§23) + Datenschutz-Härtung; Logging-Suiten 5× flake-frei | Commit reverten |
| **7** | `2717e51` | Doku + CI-Gates (`obslog.py` in `compileall`/Smoke-Import), **SI-9-Verschärfung**, dieser Bericht | Commit reverten |
| **4-Nachtrag** | `0bd9886` | Nachträglich migriert: `configuration.py` (das in Slice 4 übersehene RFC-0003-Modul) → `config.migrated` / `config.restore_failed`; totes `logger`/`import logging` entfernt | Commit reverten |

### Recovery-Slices (nach dem ersten Hosted-Run, siehe Verifikation)

| Slice | Commit | Inhalt | Rückrollpunkt |
|---|---|---|---|
| **R1** | `2d04691` | `fix(ci)`: Smoke-Harness ersetzte `logging.disable(CRITICAL)` durch kontrollierte Stream-Erfassung + Handler-Ablösung (behebt die 4 roten Fast-Gate-Tests) | Commit reverten |
| **R2** | `f8575ce` | `fix(logging)`: Schutz-/Fail-closed-Lücken — bestehende Handler neutralisiert, `propagate=False`-Logger, `handleError`, JSONL-Konsistenz, Sink-Erhalt, Schema `ts`+`logger`, D6-`location` | Commit reverten (Netz/Schema-Zusatz revertierbar) |
| **R3** | `137e994` | `test(logging)`: Sink-Regressionen für `configuration.py` (Migration/Restore) | Commit reverten |
| **R4** | _(dieser Commit)_ | `docs(logging)`: dieser Recovery-Bericht | Commit reverten |

Jeder Slice ist ein eigener, grüner, einzeln revertierbarer Commit. Es gab **keine**
absichtlich roten Commits; jeder der sechs Leckvektor-Tests (L1–L6) sowie die
Recovery-Fixes (Handler-/Fail-closed-Lücken, Sink-Erhalt, Schema, Configuration-
Regressionen) wurden vor dem Fix rot und danach grün belegt.

## Finale obslog-Schnittstelle

```python
obslog.event(name, **fields) -> None          # das EINZIGE Emit-Interface
obslog.configure(sink=None, fmt="text"|"jsonl", level=...) -> None   # nur am Startpfad
obslog.install_protection(stream=None) -> None                       # Schutznetz Legacy/Dritte
obslog.reset() / obslog.uninstall_protection()                       # Testhilfen
obslog.format_from_env(environ=None) -> "text"|"jsonl"
obslog.MemorySink                                                    # Test-Sink (.lines)
```

- `name` ist ein **benanntes Ereignis** aus einer geschlossenen Menge (`_CATALOG`);
  je Event eine **Feld-Allowlist** mit festen Transformationen.
- **Kein Freitext-Payload.** Es gibt keine Möglichkeit, roh zu loggen.
- Unbekannte/falsch getippte Felder werden **verworfen** (nur `dropped_fields=<Anzahl>`),
  **ohne** `str()`/`repr()` auf dem Rohwert aufzurufen (feindliche `__str__`/`__repr__`
  laufen nie).
- Der Test-Seam ist genau diese Schnittstelle plus ein injizierbarer Sink — **nie** die
  privaten Redaction-/Formatter-Helfer.

## Redaction-Garantien (D3/D5/D7/D8)

| Eingabe | Ausgabe |
|---|---|
| Rohe private Inhalte (Clipboard/Vault/Nutzertext) | kein Feld dafür — erscheinen auf **keinem** Level |
| Unbekannter Feldname | verworfen; nur `dropped_fields=<n>` |
| Feld mit falschem Typ | verworfen wie unbekannt (kein `str()`) |
| Unbekannter Event-Name | nie ausgegeben; neutraler Marker |
| URL | auf `schema://host` reduziert (Pfad/Query/Fragment/Userinfo weg) |
| Exception | nur `error_type`/`component`/`where` — nie Message/Traceback |
| Redaction/Formatter/Sink wirft | datenfreie Ersatzzeile; `event()` wirft nie |

## Import-Sicherheit (D9)

Der **Import** von `obslog`/`server` installiert **keinen** Handler, erzeugt **keine**
Datei und ändert die Root-Logger-Konfiguration **nicht** (im Subprozess belegt:
`ROOT_HANDLERS 0`). Die Verdrahtung (`configure` + `install_protection`) passiert
ausschließlich am Startpfad `server._configure_logging`, für beide Entry Points
(`python server.py` und `uvicorn server:app`). Logging ist **prozessweit**, kein
Runtime-Zustand.

## Legacy-/Drittanbieter-Schutznetz (§17) — Netz, keine Garantie

`install_protection()` tut zweierlei (verschärft im Recovery-Slice R2): **(1)** es hängt
einen eigenen, fail-closed Handler (`_ProtectionHandler`) an den Root-Logger, und **(2)**
es neutralisiert **alle bereits vorhandenen** Handler — an Root **und** an jedem benannten
Logger, auch `propagate=False` — mit einem sanitierenden Filter (`_SanitizingFilter`), der
den Record **in-place** bereinigt, bevor irgendein Handler ihn formatiert. Ein
zusätzlicher sicherer Handler allein genügt nicht.

Der `_ProtectionFormatter` rendert `ts logger [level] <sanitierte Nachricht>` (bzw. eine
gültige JSON-Zeile bei JSONL):

- **URLs** → Schema+Host;
- **sensible Query-Werte** (`token/key/api_key/password/secret/access_token/auth`, auch in
  bloßen Pfaden wie `uvicorn.access "GET /ws?token=…"`) → `<redacted>`;
- **Secret-Muster** (`sk-…`, `Bearer …`, JWT) → `<redacted>`;
- **Traceback/exc_text/rohe Args** werden entfernt und nie angehängt;
- **`handleError`** (auch bei `logging.raiseExceptions=True` + kaputtem Stream) gibt nie
  den Rohrecord/-Traceback aus — höchstens eine statische, datenfreie Fallback-Zeile;
- der Formatter **wirft nie** (Fallback-Zeile).

Laute INFO-Logger (`httpx`, `anthropic`, `uvicorn.access`, `httpcore`, `playwright`)
werden konservativ auf WARNING gehoben. Die **harte Garantie** liefern die
Allowlist-Ereignisse des eigenen Codes; das Netz ist die bewusst benannte Grenze (§25).

## Format, Level, Kompatibilität (D4/D10)

- Default: eine menschenlesbare Zeile pro Event nach **stderr** (Launcher-Tail bleibt
  brauchbar). JSONL via `JARVIS_LOG_FORMAT=jsonl` — **dieselben** Felder, **dieselbe**
  Redaction. Level via `JARVIS_LOG_LEVEL`.
- **Kein** neuer Sink/FileHandler, **keine** neue Dependency. Rotation/Aufbewahrung
  unverändert (Launcher). REST-/WS-/Config-/Memory-/UI-Verträge unberührt.

## Hosted-CI-Historie (Recovery)

- **Erster Hosted-Run `29605541336` (auf `0bd9886`) war ROT.** Browser-Gate grün,
  **Fast-Gate rot**: 723 Tests, **4 Failures**, 0 Errors, 0 Skips — die vier
  obslog-Schutznetz-Tests (`ProtectionNetTests` + `FaultInjectionTests.
  test_protection_formatter_survives_unrenderable_message`) mit leerem formatiertem
  Stream.
- **Ursache (Test-Harness-Konflikt, kein Produktfehler):** `scripts/smoke-test.py`
  rief vor der Suite `logging.disable(logging.CRITICAL)` auf — das unterdrückt auch
  WARNING/ERROR global, sodass die Schutznetz-Tests keinen Output erhielten. Behoben in
  R1 (`2d04691`) durch kontrollierte Stream-Erfassung statt globalem Abschalten.
- Ein PC-Ausfall stoppte lediglich einen funktionslosen CI-Monitor (er nutzte ein nicht
  installiertes externes `jq` und gab nur `jq: command not found` aus) — **keine
  Implementierung und kein Commit gingen verloren** (lokaler HEAD = Remote = `0bd9886`,
  nichts gestaged, kein Merge-/Rebase-Zustand).
- **Neuer grüner Hosted-Run auf dem Recovery-HEAD:** _wird nach dem Push ergänzt_
  (Freigabe erst, wenn Fast **und** Browser auf dem neuen Branch-HEAD grün sind).

## Verifikation (frische lokale Läufe nach allen Fixes)

- Volle Suite grün (`python -m unittest discover -s tests`): **734** Tests, 0 Failures,
  0 Errors, 0 unerwartete Skips.
- Alle sechs Leckvektoren L1–L6 mit Regressionstest am Sink-Output, je ohne Fix rot belegt.
- Recovery-Sicherheitstests (5A bestehende Handler, 5B `propagate=False`, 5C `handleError`,
  5D JSONL, 5E Lifespan-Sink-Erhalt, 5F Schema, D6 Codeort) je rot→grün belegt.
- Configuration-Producer-Regressionen (`config.migrated`/`config.restore_failed`) grün;
  Migrations-Regression rot→grün belegt.
- Fault-Injection (§23) + Import-Sicherheit (Subprozess: `ROOT_HANDLERS 0`) grün;
  Logging-Suiten 5× flake-frei; Smoke-Test grün (734 Tests, EXIT 0).
- Eingecheckte Test-Fixture `tests/fixtures/config.test.json` bytegleich unverändert.
- CI-Gates: `obslog.py` in `compileall` (`pr.yml`, `CI_PIPELINE.md`) und im
  Smoke-Import-Gate.

## Bewusst außerhalb des Scopes

- **Bestehende Logdateien** mit Altinhalten werden **nicht** gelöscht/bereinigt
  (akzeptiertes Restrisiko, §25).
- **Launcher/PowerShell** (`jarvis-launcher.pyw`, `launch-session.ps1`) bleiben vorerst
  ungeregelt (optionaler Slice 8, eigener Entscheid — nicht Teil dieser Umsetzung).
- Durchgehende **Korrelation** (`correlation_id`) bleibt offen (Phase 11).
