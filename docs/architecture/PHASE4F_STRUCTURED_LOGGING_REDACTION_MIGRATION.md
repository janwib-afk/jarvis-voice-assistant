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
| **7** | _(dieser Commit)_ | Doku + CI-Gates (`obslog.py` in `compileall`/Smoke-Import), **SI-9-Verschärfung**, dieser Bericht | Commit reverten |

Jeder Slice ist ein eigener, grüner, einzeln revertierbarer Commit. Es gab **keine**
absichtlich roten Commits; jeder der sechs Leckvektor-Tests wurde vor dem Fix rot und
danach grün belegt (Red-Green im Verlauf dokumentiert).

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

`install_protection()` hängt genau einen sanitierenden Handler an den Root-Logger. Der
`_ProtectionFormatter` rendert nur `name level <sanitierte Nachricht>`:

- **URLs** → Schema+Host;
- **sensible Query-Werte** (`token/key/api_key/password/secret/access_token/auth`, auch in
  bloßen Pfaden wie `uvicorn.access "GET /ws?token=…"`) → `<redacted>`;
- **Secret-Muster** (`sk-…`, `Bearer …`, JWT) → `<redacted>`;
- **Traceback/exc_text** werden gar nicht erst angehängt.

Laute INFO-Logger (`httpx`, `anthropic`, `uvicorn.access`, `httpcore`, `playwright`)
werden konservativ auf WARNING gehoben. Die **harte Garantie** liefern die
Allowlist-Ereignisse des eigenen Codes; das Netz ist die bewusst benannte Grenze (§25).

## Format, Level, Kompatibilität (D4/D10)

- Default: eine menschenlesbare Zeile pro Event nach **stderr** (Launcher-Tail bleibt
  brauchbar). JSONL via `JARVIS_LOG_FORMAT=jsonl` — **dieselben** Felder, **dieselbe**
  Redaction. Level via `JARVIS_LOG_LEVEL`.
- **Kein** neuer Sink/FileHandler, **keine** neue Dependency. Rotation/Aufbewahrung
  unverändert (Launcher). REST-/WS-/Config-/Memory-/UI-Verträge unberührt.

## Verifikation

- Volle Suite grün (`python -m unittest discover -s tests`): **723** Tests, 0 Skips-Regression.
- Alle sechs Leckvektoren L1–L6 mit Regressionstest am Sink-Output, je ohne Fix rot belegt.
- Fault-Injection (§23) + Import-Sicherheit (Subprozess) grün; Logging-Suiten 5× flake-frei.
- Eingecheckte Test-Fixture `tests/fixtures/config.test.json` bytegleich unverändert.
- CI-Gates ergänzt: `obslog.py` in `compileall` (`pr.yml`, `CI_PIPELINE.md`) und im
  Smoke-Import-Gate.

## Bewusst außerhalb des Scopes

- **Bestehende Logdateien** mit Altinhalten werden **nicht** gelöscht/bereinigt
  (akzeptiertes Restrisiko, §25).
- **Launcher/PowerShell** (`jarvis-launcher.pyw`, `launch-session.ps1`) bleiben vorerst
  ungeregelt (optionaler Slice 8, eigener Entscheid — nicht Teil dieser Umsetzung).
- Durchgehende **Korrelation** (`correlation_id`) bleibt offen (Phase 11).
