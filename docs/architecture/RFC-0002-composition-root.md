# RFC-0002: Composition Root — Ressourcen- und Config-Besitz

## Status

**Accepted for incremental implementation** (2026-07-15). Architektur-Kandidat 02 aus
dem Architekturbericht (`architecture-review-20260713-221830.html` — eine **nicht
versionierte** historische Evidenz, die nur temporär in `%TEMP%` erzeugt und bewusst
nicht eingecheckt wurde; nicht im Repository auffindbar), vom Nutzer in
Prompt 8A ausdrücklich gewählt; Grilling (D1–D5), „Design It Twice" (drei read-only
Entwürfe) und die Zielentwurf-Wahl (**E3 kompatibilitäts-first + E2-Zugriffsmuster**,
neue/migrierte Routen ziehen Deps aus `app.state.runtime`) sind abgeschlossen und vom
Nutzer bestätigt (2026-07-15).

> **Umsetzungsstand (aktualisiert 2026-07-19):** Diese Architektur ist **umgesetzt**.
> `runtime.py` ist der Composition Root; `create_app(runtime)` und der Lifespan
> (`aopen`/`aclose`) sind produktiv, Routen ziehen Deps aus `app.state.runtime`. Die
> ursprüngliche Vorbedingung (Phase-3-Hosted-Runner grün) war erfüllt; die Migration
> (Prompt 8, Phase 4A) und ihr voll-lazy Amendment 1 sind längst gemergt. Der folgende,
> ursprüngliche „Umsetzungsvorbehalt" ist damit **historisch**.

> Dieses RFC **implementiert nichts**. Es autorisiert (nach ausdrücklicher Annahme)
> die inkrementelle Umsetzung des Composition Roots. RFC-0001 (Action → deep module)
> bleibt **unverändert akzeptiert**, wird aber gemäß **D1 erst nach** der
> Composition-Root-Stabilisierung umgesetzt.

## Amendment 1 (2026-07-15) — Voll-lazy Import (ausdrücklich akzeptiert)

**Vom Nutzer ausdrücklich als RFC-0002-Änderung akzeptiert (2026-07-15).** Bei der
Implementierung (Prompt 8) trat ein direkter Konflikt zwischen dem ursprünglichen
E3-„eager Import-Bootstrap" (Clients/Config **beim Import**) und dem Prompt-8-Gate
(„Import lädt keine Config, erzeugt keine Clients") zutage. Dieses Amendment ersetzt
den eager-Bootstrap-Kompromiss **normativ** durch **voll-lazy Import**. Wo ältere
Passagen dieses RFC (Constraints „eager Priming"; Config-Ladezeitpunkt „Zwei-Welten-
Kompromiss"; Ressourcenbesitz-Tabelle „`from_env` (Kompat: import-sichtbar)";
Import-/App-Factory-Semantik; Adapter **A1/A5**; der „Nachgewiesen grün"-Absatz; die
Slice-Beschreibungen; das Risiko „Zwei-Welten-Konstruktion") dem widersprechen,
**gilt dieses Amendment** (die betroffenen Passagen sind unten entsprechend korrigiert).

**Verbindliche Regeln (ersetzen widersprüchliche Passagen):**
1. **`import server` lädt keine Config und erzeugt keine Clients** — kein `sys.exit`,
   kein `ai`/`http`, keine Config-I/O beim Import.
2. **`server.app` bleibt importierbar**, erhält beim Import aber nur eine **ungeöffnete
   `Runtime`** (nur `config_path` aufgelöst + `session_token` erzeugt — beides ohne I/O).
3. **Config und OWNED Clients entstehen ausschließlich im FastAPI-Lifespan** (`aopen`);
   fehlende/ungültige Produktionsconfig ⇒ Lifespan-Start schlägt geschlossen fehl
   (fails-closed); `python server.py` beendet mit Non-Zero-Exit **vor** `uvicorn.run`.
4. **Tests und E2E-Harness wechseln** auf `create_app(runtime)` bzw. einen
   lifespan-fahrenden `with TestClient(app)`; injizierte Test-Clients bleiben **BORROWED**.
5. **Adapter A1 (eager Import-Bootstrap) entfällt**; **A5** bedeutet nun: `server.http`/`ai`
   existieren erst **nach** Lifespan-Start (bzw. wenn injiziert). Der `_wired`-Latch bleibt
   (Idempotenz + Schutz injizierter Fakes), aber es gibt **kein** eager `wire()` beim Import.
6. **Wire-, REST-, WS-, Config- und Memory-Verträge bleiben byte-/shape-unverändert.**

Falls die sieben vorgesehenen Testmigrationen nicht ausreichen oder ein bestehender
öffentlicher Entry Point (`server.app`, `python server.py`, Launcher, `uvicorn server:app`)
nicht erhalten werden kann, wird die Umsetzung mit konkretem Befund **gestoppt** statt den
Scope still zu erweitern.

## Zusammenfassung

Der heutige „Composition Root" ist der **Import von `server.py`**: beim `import server`
werden Config geladen (`sys.exit(1)` bei Fehler), `ai`/`http`-Clients erzeugt, vier
Module verdrahtet, die FastAPI-App gebaut, veraltete `on_startup`/`on_shutdown`-Hooks
registriert und ein untracked Background-Task gestartet. `ai`/`http` werden **nie**
geschlossen (Leak, besonders bei Import-/Startup-Fehler). Dieses RFC konzentriert
Verdrahtung und Ressourcen-Lebenszyklus hinter ein kleines Composition-Root-Interface:
ein **`Runtime`**-Objekt (Besitz + Lifecycle) und eine **seiteneffektfreie
`create_app(runtime)`-Factory**, deren Ressourcen ein **FastAPI-Lifespan** öffnet und
deterministisch schließt. Alle bestehenden Wire-Verträge (REST, WS, `[ACTION:…]`,
Config/Memory) und alle Entry Points (`server.app`, `python server.py`, Launcher,
`TestClient(server.app)`, CI) bleiben **byte-/shape-identisch**. Migration in fünf
kleinen, einzeln rückrollbaren vertikalen Slices.

## Nachprüfbare Code-Evidenz

Alle Import-Seiteneffekte in `server.py` (beim `import server`):

| Seiteneffekt | Ort |
|---|---|
| `sys.stdout/stderr.reconfigure` | `server.py:10-11` |
| `SESSION_TOKEN = secrets.token_urlsafe(24)` | `server.py:44` |
| Config-Pfad auflösen | `server.py:50-52` |
| `config = config_loader.load_config(...)` + `sys.exit(1)` bei Fehler | `server.py:53-57` |
| `STARTUP_WARNINGS = check_runtime_environment(config)` | `server.py:61-63` |
| `ai = anthropic.AsyncAnthropic(...)`, `http = httpx.AsyncClient(...)` | `server.py:66-67` |
| 4× Wiring: `memory.configure` / `assistant_core.configure` / `assistant_core.init_clients` / `app_launcher.configure` | `server.py:70-76` |
| `app = FastAPI()` | `server.py:78` |
| `app.router.on_shutdown.append(browser_tools.close)` | `server.py:84` |
| `app.router.on_startup.append(_startup_refresh)` (untracked `create_task`) | `server.py:87-96` |
| `ws_clients: set = set()` | `server.py:99` |
| `assistant_core.PERSIST_LAUNCHER = persist_launcher_block` | `server.py:498` |

Verteilte konfigurierbare Modul-Globals: `assistant_core` Persona/City/TTS + Kontext-Cache
+ `conversations`/`pending_confirm` (`assistant_core.py:37-63`); `app_launcher.APPS/PROFILES/
ACTIVE_PROFILE` (`app_launcher.py:45-47`); `memory.VAULT_PATH/INBOX_PATH` (`memory.py:24-25`);
Browser-Singleton `browser_tools._pw/_browser/_context` (`browser_tools.py:20-22`).

**Kompatibilitätskritischer Befund (steuert den Entwurf):** Kein Bestandstest fährt die
App-Lifespan — `TestClient(server.app)` wird durchgängig **ohne** `with` genutzt
(`tests/test_ws.py:44`, `tests/test_settings_api.py:60`, `scripts/smoke-test.py:123`);
`websocket_connect` triggert die Lifespan ebenfalls nicht. Deshalb entstehen die
import-lesbaren Symbole (`server.config`, `server.CONFIG_PATH`, `server.SESSION_TOKEN`,
`server.http`) heute **beim Import**. `e2e_server.py` monkeypatcht sogar
`config_loader.load_config` **vor** `import server` (`tests/browser/e2e_server.py:100-101`)
und liest danach `server.http`/`server.CONFIG_PATH` und hängt Routen an `server.app`.

## Problemstellung und aktueller Zustand

Der Import verrichtet Arbeit statt nur zu definieren: er lädt I/O-Config, erzeugt
Netzwerk-Clients, verdrahtet vier Module und kann den Prozess beenden (`sys.exit`).
Folgen: (1) **Leak** — `ai`/`http` haben keinen Besitzer, der sie schließt; ein
Import-/Startup-Fehler nach ihrer Erzeugung lässt offene Clients zurück. (2) **Keine
Isolation** — jeder Zustand ist prozessweit; zwei App-Instanzen im selben Prozess sind
nicht trennbar. (3) **Testkopplung** — Tests koppeln an `import server` + Global-Patching;
das E2E-Harness muss `load_config` vor dem Import monkeypatchen. (4) **Veraltete
Lifecycle-Mechanik** — `on_startup`/`on_shutdown` statt `lifespan`; ein Background-Task
ohne Cancellation-Handle.

## Betroffene Ressourcen und Zustände

| Ressource/Zustand | heute Besitzer | Ziel-Besitzer |
|---|---|---|
| Config + `CONFIG_PATH` + Warnings | `server`-Modul-Global (Import) | `Runtime` (geladen im Lifespan; Modul-Global bleibt **K05-Residual**) |
| `ai` (Anthropic), `http` (httpx) | `server`-Modul-Global (Import) | `Runtime` (OWNED/BORROWED, D3) |
| Browser (`_pw/_browser/_context`) | `browser_tools`-Modul-Global | `Runtime` besitzt **Lifecycle** (D4); Instanz bleibt Residual |
| `SESSION_TOKEN`, `ws_clients` | `server`-Modul-Global | `Runtime` (per-App) |
| `conversations`, `pending_confirm` | `assistant_core`-Modul-Global | `Runtime` (per-App; Semantik unverändert) |
| Refresh-Task | untracked `create_task` | `Runtime._refresh_task` (getrackt, cancelbar) |
| Persona/City/TTS, `APPS/PROFILES`, `VAULT_PATH`, Health-Cache | Modul-Globals via `configure()` | Lifecycle-Owner = `Runtime` (einziger `configure()`-Caller); Speicher bleibt im Modul (schmaler Adapter) |

## Invarianten (müssen byte-/shape-erhalten bleiben)

Alle REST-Pfade/Request-/Response-Formen; das WebSocket-Protokoll inkl. Frame-Typen
(`health`/`response`/`action`/`error`/`stop` + Broadcasts) und deren Reihenfolge;
`[ACTION:…]` + alle 22 Action-Typen; Stop-/Cancel- und Confirmation-Verhalten;
App-Allowlist; Profile/Placement; Config- und Memory-Dateiformat; Frontenddarstellung;
Launcher-/Startverhalten; lokale Bindung `127.0.0.1`; Origin-/Token-Prüfung; alle
Security-Invarianten (SI-1…SI-9, threat model). **Keine** neuen produktiven Modul-Globals
im migrierten Bereich; **kein** Service-Locator/String-Lookup; **keine** „get anything"-
Methode.

## Ziele

- FastAPI-App **import-sicher** über eine explizite Factory erzeugbar.
- Import lädt keine Config, erzeugt keine Clients, startet keine Prozesse/Tasks, ruft kein
  `sys.exit`.
- Produktion und Tests nutzen **dieselbe** App-Erzeugung mit unterschiedlichen kontrollierten
  Eingaben.
- Ressourcen werden im **Lifespan** geöffnet und geschlossen; `ai`/`http` bekommen einen
  Besitzer (Leak behoben).
- Config, Clients und per-App-Laufzeitzustand haben **einen** eindeutigen Besitzer (`Runtime`).
- Mehrere App-Instanzen sind (für die migrierten Ressourcen) isoliert.
- Bestehende Startbefehle, Browserclients und alle Wire-Verträge bleiben kompatibel.

## Nicht-Ziele

- **Kein** Conversation-Session-deep-module (Kandidat 03) — `conversations`/`pending_confirm`
  wandern nur im **Besitz**, ihre Semantik bleibt identisch.
- **Kein** Settings-Live-Apply-Single-Writer (Kandidat 05) — `config` bleibt vorerst
  Modul-Global (Residual); der Save-Pfad ändert sich nicht.
- **Kein** LLM-deep-module-Interface (`complete/summarize`, Kandidat 04) — der Root besitzt
  nur den **Client-Lifecycle**, nicht dessen Interface.
- **Keine** Action-Migration (RFC-0001), **kein** per-App-Browser (D4-Residual), **keine**
  Protokoll-/Config-Schema-/DB-Änderung, **kein** Capability-/Policy-Kernel, **kein**
  Scheduler/Connector, **keine** UI-Änderung, **keine** Entfernung von `[ACTION:…]`.
- **Keine** `protocol_version`/`event_id`/`correlation_id`/`schema_version`.

## Constraints

- Windows / CPython 3.10+ (SYSTEM_CHARTER); Bind nur `127.0.0.1`.
- Standardtests kosten 0 Provider (QUALITY_BASELINE); LLM/TTS/Browser gemockt.
- `core.autocrlf=true` ohne `.gitattributes` → Slices klein halten (Diff-Lesbarkeit).
- Nur vertikale, einzeln rückrollbare Slices; kein Big-Bang.
- D5-Realität (per **Amendment 1**): Import erzeugt nur eine **ungeöffnete** Runtime
  (`config_path` + `session_token`, keine I/O); Config + OWNED-Clients öffnen ausschließlich im
  Lifespan. Bestandstests, die `server.config`/`server.http` **ohne** Lifespan lasen, werden auf
  `with TestClient(create_app(runtime))` migriert (7 Dateien).

## Betrachtete Entwurfsvarianten

Drei read-only-Entwürfe (Design It Twice):

- **E1 — Minimal:** zwei Symbole (`Runtime`-dataclass + `create_app`); Verhalten
  (`apply_settings`/`broadcast`/`persist`) bleibt in `server.py`. Kleinste Fläche, aber
  Risiko im Global→Property-Slice; unterschreitet den in D2 gewählten Besitz-Umfang.
- **E2 — Explizites Runtime:** `Runtime` mit Methoden; **jede** Route zieht Deps via
  `Depends(get_runtime)`/`app.state.runtime`; Modulklassen-Property-Bridge für Bestandstests.
  Eleganteste Endform + stärkste Isolation, aber größerer Diff, höheres Migrationsrisiko,
  „magische" Bridge.
- **E3 — Kompatibilitäts-first:** `Runtime` + `create_app`, Verhalten in `Runtime`,
  namens-identische Read-Aliase, fünf byte-erhaltende Slices mit pro-Aufrufer-Grün-Nachweis,
  Deletion-Tests + CI-grep-Guard. Kleinstes Pro-Slice-Risiko, stärkste Kompatibilität.

## Ausgewählte Entscheidung mit Begründung

**Gewählt: E3-Basis + E2-Zugriffsmuster.** E3 liefert das kleinste Pro-Slice-Risiko, den
stärksten Kompatibilitätsnachweis und die beste Löschdisziplin; es erfüllt D2 (Runtime
besitzt per-App-State, ist einziger `configure()`-Caller und trägt das Verhalten). Aus E2
wird das **`app.state.runtime`-Zugriffsmuster** übernommen: neue/migrierte Routen ziehen ihre
Deps aus dem Runtime-Handle statt aus Modul-Globals, sodass **neue Produktionspfade
ausschließlich die neue Seam** nutzen. Die vollständige `Depends(get_runtime)`-Umstellung
**aller** Routen bleibt optional für später (kleiner Diff jetzt). E2 pur wäre die eleganteste
Endform, aber teurer/riskanter; E1 pur trägt das Verhalten nicht im Runtime (unterschreitet D2).

### Bestätigte Grilling-Entscheidungen

- **D1 — Reihenfolge:** Der Composition Root wird **vollständig stabilisiert, bevor** die
  RFC-0001-Migration (Action → deep module) beginnt.
- **D2 — Besitz-Umfang:** Root besitzt Config-Laden, LLM-/HTTP-/Browser-Client-Lifecycle,
  App-Factory + Lifespan, per-App-Laufzeitzustand (`SESSION_TOKEN`, `ws_clients`,
  `conversations`, `pending_confirm`) und ist **einziger** `configure()`-Caller; Semantik
  unverändert.
- **D3 — owned/borrowed:** injizierte Clients = **borrowed** (nie vom Root geschlossen);
  selbst erzeugte = **owned** (im Lifespan geschlossen).
- **D4 — Browser:** Root besitzt den **Lifecycle**; `browser_tools`-Instanz bleibt vorerst
  modul-globaler Lazy-Singleton (per-App-Browser = Residual).
- **D5 — Entry-Point/Config-Zeitpunkt** (präzisiert durch **Amendment 1**): `server.app` bleibt
  import-sicher und erhält beim Import nur eine **ungeöffnete** Runtime (keine Config-I/O, keine
  Clients); `create_app()` reine Verdrahtung; Config-Laden + Client-Öffnen ausschließlich im
  Lifespan; fehlende Config → Startup **fails-closed** (kein `sys.exit` beim Import).

## Zielarchitektur

- Ein neues Modul **`runtime.py`** definiert **`Runtime`** — den einzigen Besitzer von Config,
  Clients, per-App-State und Lifecycle.
- **`create_app(runtime) -> FastAPI`** (in `server.py`) ist reine, seiteneffektfreie
  Verdrahtung: Routen registrieren, `StaticFiles` mounten, `app.state.runtime = runtime`
  setzen, `lifespan=runtime.lifespan` binden.
- Der **Lifespan** öffnet (Startup) und schließt (Shutdown) die Ressourcen deterministisch.
- Bestehende Module (`assistant_core`/`app_launcher`/`memory`) bleiben mit ihren
  `configure()`-Funktionen; der Root ist ihr einziger Aufrufer (schmaler Adapter).

## Öffentliche Composition-Root-Schnittstelle

```python
# runtime.py
@dataclass
class Runtime:
    config_path: str
    config: dict | None                 # None ⇒ fails-closed (kein sys.exit)
    startup_warnings: list[str]
    session_token: str                  # per-App
    ws_clients: set                     # per-App, in-place mutiert
    ai: object                          # OWNED, außer injiziert (BORROWED)
    http: object                        # OWNED, außer injiziert
    owns_clients: bool                  # D3
    # privat: _wired, _refresh_task, _closed

    @classmethod
    def from_env(cls, environ=os.environ, *, default_config_path,
                 load=config_loader.load_config, ai=None, http=None) -> "Runtime":
        """Pfad auflösen, Config best-effort laden (KEIN sys.exit; Fehler ⇒
        config=None + Warnung), Token erzeugen, Clients adoptieren (BORROWED)
        oder konstruieren (OWNED)."""

    def wire(self) -> None:
        """EINZIGER Aufrufer von memory.configure/assistant_core.configure/
        assistant_core.init_clients/app_launcher.configure + PERSIST_LAUNCHER-Injektion.
        Idempotent (_wired-Latch): schützt e2e-Overrides nach dem Import."""

    @asynccontextmanager
    async def lifespan(self, app):      # FastAPI(lifespan=…)
        await self.aopen(); yield; await self.aclose()

    async def aopen(self) -> None       # fails-closed prüfen, wire() falls nötig, Refresh-Task starten
    async def aclose(self) -> None      # idempotent, partial-failure-fest

    # aus server.py hierher gezogen (Signatur identisch):
    async def apply_settings(self, merged: dict) -> None
    async def broadcast_json(self, payload: dict) -> None
    async def broadcast_health(self) -> None
    async def persist_launcher_block(self, new_launcher: dict, kind: str) -> list[str]
```

```python
# server.py
def create_app(runtime: Runtime) -> FastAPI:   # reine Verdrahtung, seiteneffektfrei
    app = FastAPI(lifespan=runtime.lifespan)
    app.state.runtime = runtime
    app.mount("/static", StaticFiles(...))
    # … alle @app-Routen (byte-identische Handler-Rümpfe) …
    return app

def get_runtime(request: Request) -> Runtime:   # FastAPI-Dependency für neue/migrierte Routen
    return request.app.state.runtime
```

Öffentliche Fläche = **`Runtime`** + **`create_app`** (+ die kleine `get_runtime`-Dependency).
Alles Ownership-/Lifecycle-Detail liegt dahinter.

## Verborgene Implementierungsdetails

Owned/Borrowed-Buchführung (`owns_clients`); `_wired`-Latch (genau-einmal-Verdrahtung, schützt
e2e-Overrides); `_closed`-Latch (idempotentes Close); `_refresh_task`-Handle; Token-Erzeugung;
fails-closed-Repräsentation (`config=None`); die Reihenfolge von `resolve_config_path`/
`load_config`/`check_runtime_environment` (die Funktionen selbst bleiben in `config_loader`).
Die Kompatibilitäts-Read-Aliase (`server.config`/`server.http`/…) sind ein technisches Detail,
**nicht** Teil des öffentlichen Interface.

## Dependency-Richtung und Adapter

- **Richtung:** Routen/WS ziehen Deps aus `app.state.runtime` (neue/migrierte) — nie aus
  Modul-Globals. `assistant_core` erhält seinen Persist-Hook weiter per Injektion
  (`PERSIST_LAUNCHER = runtime.persist_launcher_block`) statt per Import (vermeidet den
  Zirkular-Import wie heute, `server.py:498`).
- **Kein Service-Locator:** `app.state.runtime` ist ein typisiertes Objekt, injiziert über
  `create_app(runtime)` — kein String-Lookup, keine „get anything"-Methode.
- **Kompatibilitätsadapter** (dünn, dokumentiert; siehe Kompatibilitätsstrategie).

## Config-Besitz und Config-Ladezeitpunkt

- `config_loader` bleibt das Leaf-Modul (Format/Validierung/atomarer Save unverändert).
- `Runtime.from_env` orchestriert `resolve_config_path` → `load_config` (best-effort, **kein
  `sys.exit`**) → `check_runtime_environment`. Fehler ⇒ `config=None` (+ Warnung).
- Der **`JARVIS_CONFIG_PATH`-Seam** (ADR 0003) bleibt der explizite Produktions-/Test-Selektor;
  **kein** stiller Fallback auf Testwerte.
- **Voll-lazy Import (Amendment 1):** Beim Import wird **keine** Config geladen und **kein**
  Client erzeugt. `Runtime.for_production(...)` löst nur den `config_path` auf und erzeugt den
  `session_token` — beides ohne I/O. `Runtime.load_config()` und die OWNED-Client-Erzeugung laufen
  **ausschließlich** im Lifespan (`aopen`). Fehlende/ungültige Produktionsconfig ⇒ `aopen` schlägt
  geschlossen fehl (fails-closed); kein `sys.exit` beim Import.

## Ressourcenbesitz und Lebenszyklus

| Ressource | Besitz | Öffnen | Schließen |
|---|---|---|---|
| `ai`/`http` selbst erzeugt | OWNED | **`aopen` (Lifespan)** — nie beim Import (Amendment 1) | `aclose`: SDK-nativer async-Close, nur wenn OWNED |
| `ai`/`http` injiziert | BORROWED | `create_app(Runtime(..., ai=…, http=…))` | **nie** |
| Browser | Lifecycle-Owner = Runtime (D4) | lazy im ersten Action-Call | `aclose`: `browser_tools.close()` (ersetzt `on_shutdown`) |
| Refresh-Task | OWNED | `aopen` (außer `JARVIS_SKIP_STARTUP_REFRESH`) | `aclose`: cancel + await + suppress |
| `session_token`/`ws_clients`/`conversations`/`pending_confirm` | per-App, OWNED | `from_env` | mit dem Runtime-Objekt |
| Persona/City/TTS, `APPS/PROFILES`, `VAULT_PATH`, Health-Cache | Lifecycle-Owner = Runtime; Speicher = Modul | `wire()` | — |

**Öffnen-Reihenfolge (`aopen`):** (1) fails-closed prüfen (`config is None`) → (2) `wire()`
falls `not _wired` → (3) Refresh-Task starten.
**Schließen-Reihenfolge (`aclose`, umgekehrt, jeder Schritt eigen-guarded):** (1) Refresh-Task
`cancel()`+`await` (suppress CancelledError) → (2) `browser_tools.close()` → (3) OWNED `http`
schließen → (4) OWNED `ai` schließen → `_closed=True`.

## Import- und App-Factory-Semantik

`create_app(runtime)` ist **seiteneffektfrei** (nur Verdrahtung). `app = create_app(runtime)`
darf auf Modulebene stehen und ist import-sicher, weil Config-Laden **und** Client-Öffnen
**ausschließlich** im Lifespan (`aopen`) passieren — beim Import wird nur eine **ungeöffnete**
Runtime erzeugt (Amendment 1). `server.app` bleibt ein importierbares ASGI-App-Objekt
(`uvicorn server:app`, `python server.py`, `TestClient(server.app)`). Bestandstests, die
`server`-Zustand **ohne** Lifespan lasen, fahren ihn nun via `with TestClient(app)`.

## Startup-, Partial-Failure- und Cleanup-Verhalten

```python
async def aopen(self):                           # Amendment 1: Config + Clients erst HIER (Lifespan)
    if self.config is None:
        self.load_config()                       # ConfigError ⇒ fails-closed (kein sys.exit)
    if self.http is None:                         # OWNED-Client erst hier erzeugen
        self.http = httpx.AsyncClient(timeout=30); self.owns_clients = True
    if self.ai is None:
        self.ai = anthropic.AsyncAnthropic(api_key=self.config["anthropic_api_key"],
                                           timeout=30.0, max_retries=2)
    assistant_core.init_clients(self.ai, self.http)
    if not self._wired: self.wire()
    if not os.environ.get("JARVIS_SKIP_STARTUP_REFRESH"):
        self._refresh_task = asyncio.create_task(asyncio.to_thread(assistant_core.refresh_data))

async def aclose(self):
    if self._closed: return
    self._closed = True
    t = self._refresh_task
    if t and not t.done():
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception): await t
    for step in (self._close_browser, self._close_http, self._close_ai):
        with contextlib.suppress(Exception): await step()
```

- **Partial-Failure:** Der Lifespan-`finally` ruft `aclose` **immer** — bricht `aopen` nach dem
  Refresh-Start ab, werden bereits geöffnete OWNED-Ressourcen geschlossen (kein Leak).
- **Idempotenz:** `_closed`-Latch; doppelter `aclose` ist no-op.
- **Fails-closed vs. `sys.exit`:** Import wirft nie; `python server.py` `sys.exit`et im `__main__`
  bei `runtime.config is None` (exakte Launcher-„exited"-Semantik erhalten); `uvicorn server:app`
  → `aopen`-`raise` → uvicorn beendet den Prozess (kein `/health`; Launcher behandelt das wie
  heute).

## Cancellation und Shutdown

Der bisher untracked Refresh-Task (`server.py:94`) bekommt ein Handle (`_refresh_task`) und wird
im `aclose` gecancelt und abgewartet. Das WS-Worker-/Queue-/Stop-Verhalten (`server.py:142-211`)
bleibt **unverändert**; `end_session` räumt Conversation + Pending Confirmation weiter auf. Ein
sauberer Shutdown wartet auf das Cleanup (kein verwaister Task).

## Parallelität und Isolation mehrerer App-Instanzen

`create_app(runtime)` isoliert **sofort** die runtime-nativen Felder (`session_token`,
`ws_clients`, `config`, `ai`/`http`, App-Objekt/`app.state`, Lifespan). **Ehrliche Grenze:**
Zustand, der noch als Modul-Global via `configure()` lebt (Persona/City, `APPS/PROFILES`,
`VAULT_PATH`, Health-Cache) sowie `conversations`/`pending_confirm`, wird vom Runtime
**besessen und gesetzt**, aber zwei **gleichzeitig laufende** Instanzen teilen dieselbe
Modulvariable. Deshalb: **serielle** Isolationstests (Isolation in der Zeit, mit sauberem
Reset). Voll-parallele Isolation ist das Residual, das K03/RFC-0001 einlösen — der Runtime ist
dessen Voraussetzung. Dieser Grad wird in `PHASE4_COMPOSITION_ROOT_MIGRATION.md` explizit
dokumentiert, damit keine falsche „zwei Server parallel"-Erwartung entsteht.

## Security- und Credential-Invarianten

- Bind nur `127.0.0.1` (ADR 0001) — unverändert; Origin-/Token-Prüfung (`is_origin_acceptable`,
  `compare_digest`) unverändert.
- **Secrets:** API-Keys erreichen nie das Frontend; `POST /settings` lehnt Key-Felder ab; keine
  Secret-Werte in Logs/Fehlern/Fixtures (SI-5). `Runtime.from_env` gibt bei ConfigError nur
  Schlüsselnamen aus (via `config_loader`), nie Werte.
- Owned/Borrowed-Regel verhindert versehentliches Schließen fremder (Test-)Clients.
- Keine öffentliche Netzwerkbindung, kein dynamisches Laden unbekannter Module (SYSTEM_CHARTER).

## Testoberfläche und Test-Seams

- **Neu (bevorzugt):** `create_app(Runtime.from_env(env, default_config_path=FIXTURE, ai=FakeAI(),
  http=FakeHttp()))` — injizierte Fakes sind BORROWED; `with TestClient(app)` fährt `aopen/aclose`.
  Ersetzt langfristig `import server` + Global-Patching.
- **Bleibt (SEAM-REST/WS/CONVERSATION, `TEST_SEAMS.md`):** die bestätigten Seams unverändert; die
  Bestandstests, die Modul-Globals patchen, bleiben **grün** (siehe Kompatibilitätsstrategie) und
  werden **nicht** gelöscht.
- **Neue Lifecycle-/Isolationstests:** Import-Side-Effect-Freiheit, owned/borrowed-Close,
  Partial-Failure-Cleanup, Refresh-Task-Cancellation, zwei serielle isolierte Runtimes — kritische
  davon ≥5× flakefrei.

## Kompatibilitätsstrategie

Namen bleiben identisch (keine neuen produktiven Modul-Globals — nur der eine `runtime`-Handle +
Read-Aliase mit bestehenden Namen). Dünne, dokumentierte Adapter:

| # | Adapter (in `server.py`) | Alter Aufrufer | Deprecation-Bedingung | Früheste Entfernung |
|---|---|---|---|---|
| A1 | **entfällt (Amendment 1)** — kein eager Import-Bootstrap; Import erzeugt nur eine ungeöffnete Runtime (`config_path`+`session_token`, keine I/O) | — | — | entfallen |
| A2 | `app = create_app(runtime)` (Modul-`app`) | `server.app`, `uvicorn server:app`, e2e `@server.app.post` | — | **bleibt** (öffentlicher Entry) |
| A3 | `SESSION_TOKEN = runtime.session_token` (Read-Alias) | `server.SESSION_TOKEN` | Tests lesen Runtime | nach Test-Migration |
| A4 | `ws_clients = runtime.ws_clients` (dasselbe Set) | Broadcast/Routen | Routen lesen `app.state.runtime` | Slice-5-Abschluss |
| A5 | `http`/`ai` existieren **erst nach Lifespan-Start** (bzw. injiziert) — kein Import-Alias (Amendment 1) | migriertes `e2e_server` nutzt `create_app(runtime)` + lifespan-`TestClient` | e2e liest Runtime | erledigt mit dieser Migration |
| A6 | `config`/`CONFIG_PATH`/`STARTUP_WARNINGS` (Modul-Global, Source-of-Truth) | Routen + `test_*` patchen sie | **K05** (Settings-Single-Writer) | **erst mit K05** |
| A7 | `apply_settings`/`broadcast_*`/`persist_launcher_block` als Modul-Funktionen, die an `runtime.*` delegieren | Routen, `PERSIST_LAUNCHER` | Routen/Core rufen Runtime | nach Slice 4 |
| A8 | `__main__`: `sys.exit(1)` bei `config is None` **vor** `uvicorn.run` | `python server.py` (Launcher-„exited") | Launcher liest nur `/health` | Launcher-Änderung nötig |

Jeder Adapter trägt im Code einen `# DEPRECATED(K05/K03/D4/Test-Migration): …`-Marker; ein
CI-grep-Guard (`server.SESSION_TOKEN`/`server.http`/`server.config` in `tests/`) macht die
Löschreife messbar (0 Treffer ⇒ Alias entfernbar).

**Migrationsbedarf (Amendment 1):** 7 Testdateien lasen `server.config`/`server.http`/
`server.CONFIG_PATH` **ohne** Lifespan und werden auf einen lifespan-fahrenden
`with TestClient(create_app(runtime))` bzw. injizierte BORROWED-Fakes umgestellt:
`test_config_seam`, `test_settings_api`, `test_music_api`, `test_dashboard_api`,
`test_launcher_api`, `test_ws`, `tests/browser/e2e_server.py`. Der `_wired`-Latch schützt
injizierte Fakes vor Re-Wiring; `test_voice_launcher` (`PERSIST_LAUNCHER`-Signatur) und
`test_conversation_ws` (fahren bereits einen Dialog über die WS-Seam) bleiben inhaltlich
unverändert. Wire-/Frame-/Config-/Memory-Formen bleiben byte-/shape-identisch.

## Inkrementelle, vertikale Migrationsschritte

Jeder Slice = ein Commit; „grün" = `python -m unittest discover -s tests` + `python scripts/
smoke-test.py` + (nach Bedarf) Browser-Smoke + `verify_phase4/5`. Rollback = Commit revert.

> **Amendment 1** ersetzt den eager-Bootstrap: die Slices erzeugen beim Import nur eine
> **ungeöffnete** Runtime; Config + Clients öffnen im Lifespan; die 7 lifespan-losen Tests werden
> migriert. Bündelung in wenige vertikale Slices (statt Read-Alias-Zwischenstände).

- **Slice 1 — Import-sichere Factory + `runtime.py` + Lifespan (Kern).** `runtime.py` mit `Runtime`
  (`for_production`/`load_config`/`wire`/`lifespan`/`aopen`/`aclose` + `apply_settings`/`broadcast_*`/
  `persist_launcher_block`). `server.py`: `create_app(runtime)` (reine Verdrahtung, `lifespan=`), Modul
  `runtime = Runtime.for_production(...)` (ungeöffnet — keine I/O/Clients), `app = create_app(runtime)`;
  `ai`/`http`-Erzeugung + Config-Load + `configure`/`init_clients` + Refresh-Task wandern in `aopen`;
  `browser_tools.close` + OWNED-Client-Close + Task-Cancel in `aclose`; `on_startup`/`on_shutdown`-Hooks
  und der Import-`sys.exit`/Client-Bau entfallen; `__main__` fail-fast vor `uvicorn.run`. *Prüft:*
  Import-Side-Effect-Freiheit, Factory, Lifespan-Open/Close, owned/borrowed, Refresh-Cancel. *Rollback:*
  `runtime.py` entfernen + `server.py`-Diff reverten.
- **Slice 2 — 7 lifespan-lose Tests migrieren.** `test_config_seam`, `test_settings_api`, `test_music_api`,
  `test_dashboard_api`, `test_launcher_api`, `test_ws`, `tests/browser/e2e_server.py` fahren nun
  `with TestClient(create_app(runtime))` bzw. `create_app(Runtime(..., ai=FakeAI(), http=FakeHttp()))`.
  Injizierte Clients = BORROWED. *Prüft:* Bestandsverhalten byte-/shape-identisch über die Seams.
  *Rollback:* je Testdatei zurück.
- **Slice 3 — Per-App-State + Multi-App-Isolationstests.** `session_token`/`ws_clients`/`conversations`/
  `pending_confirm` als Runtime-Felder; `wire()` aliast `assistant_core.conversations/pending_confirm` an
  die Runtime-Dicts (Semantik unverändert). Neue Tests: zwei Runtimes → getrennte Felder, keine Mutation
  A↔B; ≥5× flakefrei. *Rollback:* Felder/Tests zurück.
- **Slice 4 — E2-Zugriff für neue/migrierte Routen (`app.state.runtime`) + Doku.** Wo risikoarm lesen
  Routen `request.app.state.runtime` statt Modul-Global (`_settings_token_ok` → `runtime.session_token`);
  `PHASE4_COMPOSITION_ROOT_MIGRATION.md`. *Rollback:* Route-weise zurück.

`config`/`CONFIG_PATH`/`STARTUP_WARNINGS` bleiben **Source-of-Truth-Modul-Globals** (A6-Residual, K05);
Reihenfolge respektiert **D1** und lässt K03/K04/K05 unangetastet.

Reihenfolge respektiert **D1** (Root vor RFC-0001) und lässt K03/K04/K05 unangetastet.

## Rollback je Migrationsschritt

Jeder Slice ist ein eigener revertierbarer Commit; die Read-Aliase halten Zwischenstände lauffähig,
sodass jeder Schritt ohne Wirkung auf die übrigen zurückgenommen werden kann. Vor jedem Slice ist der
letzte grüne Stand (Suite + Smoke) der Rückrollpunkt. Kompatibilitätsadapter werden erst entfernt, wenn
ihr Deletion-Test (CI-grep = 0 Treffer) und die volle Prüfung grün sind.

## Observability

Bestehendes Logging bleibt (z.B. `logger.info("Client verbunden")`, Startup-Warnungen). Neu:
Lifespan-Log „Startup ok/Shutdown ok" auf INFO ohne Secrets. **Keine** strukturierten Logs/
Korrelation (Phase 9/11). Keine Gesprächsinhalte/Screens/Clipboard in Standardlogs
(Charter-Invariante).

## Risiken und offene Fragen

- **Adapter-Verstetigung (Haupt­risiko):** A6/A7 hängen an K05, A4 an Slice-5-Abschluss,
  `conversations`/`pending_confirm` an K03, Browser-Singleton an D4. **Mitigation:** `# DEPRECATED(K0x)`-
  Marker + CI-grep-Guard + Deletion-Test.
- **Test-Migration (Amendment 1):** 7 Dateien wechseln auf lifespan-fahrende `TestClient`/Factory.
  Risiko: eine übersehene `server.config`/`server.http`-Lesung **ohne** Lifespan bricht → durch die
  Import-Side-Effect-Tests + volle Suite abgesichert; bei Nichtausreichen wird mit **konkretem
  Befund gestoppt** (kein stiller Scope-Zuwachs).
- **`_wired`-Latch:** garantiert genau-einmal-Verdrahtung im Lifespan und schützt injizierte Fakes
  vor Re-Wiring; in einem gezielten Test festgenagelt.
- **Unvollständige Parallel-Isolation** (siehe oben) — bewusst, dokumentiert, seriell getestet.
- **Offen (Impl-Detail, in Slice 1 zu fixieren):** exakter SDK-Close von `AsyncAnthropic`
  (`close()`/`aclose()`); `ctx`-Form-Fragen sind RFC-0001-Thema, nicht hier.

## Interaktion und Reihenfolge mit RFC-0001

**D1: Der Composition Root wird vor der RFC-0001-Umsetzung stabilisiert.** RFC-0001 bleibt unverändert
akzeptiert. Nutzen der Reihenfolge: RFC-0001s Actions bekommen einen sauberen Besitzer/`ctx` (Clients
via Runtime/Lifespan) statt Modul-`ai`; die `ctx`-Naht aus RFC-0001 kann später den `Runtime`-LLM-Zugriff
durchreichen. RFC-0002 fasst **keine** Action-Interna an; RFC-0001 fasst **keine** Composition-Root-
Ressourcen an — die RFCs sind disjunkt und additiv.

## ADR-Bezüge

- **Kein prior ADR autorisiert den Composition Root** (ADR 0001 Deployment, 0002 Provider-Strategie,
  0003 Test-Config-Seam, 0004 Trust, 0005 Credentials, 0006 Browser-Tests). **Dieses RFC ist der
  Entscheidungsdatensatz** (wie RFC-0001 seiner).
- **Kein neues ADR nötig** (die drei Kriterien sind nicht gemeinsam erfüllt: die Umsetzung ist bewusst
  inkrementell/rückrollbar — nicht teuer zurückzunehmen —, und der reale Trade-off E1/E2/E3 ist in
  diesem RFC vollständig festgehalten). Sollte sich während der Umsetzung eine überraschende,
  schwer rücknehmbare Entscheidung ergeben, wird ein ADR **mit Nutzerbestätigung** nachgezogen.
- **Beziehungen:** stützt ADR 0001 (Bind 127.0.0.1 bleibt), ADR 0002 (owned/borrowed-Clients passen
  zum Provider-Adapter-Ziel), ADR 0003 (`JARVIS_CONFIG_PATH` bleibt der Config-Selektor). Kein Konflikt.

## Implementierungs- und Freigabe-Gates

- **Je Slice:** gezielter Test rot→grün; volle Suite grün; Smoke Exit 0, 0 unerwartete Skips; keine
  WS-/REST-/Prompt-/UI-Regression (Browser-Smoke + `verify_phase4/5` nach betroffenen Slices);
  `git diff --check` sauber; Slice einzeln rückrollbar.
- **Prompt-8-Gate (Umsetzung):** import-sichere Factory; Import lädt keine Config/Clients/Prozesse;
  Produktion fails-closed; Tests nutzen synthetische Config + Deps; Lifespan öffnet/schließt kontrolliert;
  klare Ownership; Multi-App-Isolation (seriell) belegt; Cleanup bei Partial-Failure; Launcher +
  bestehender Browser laufen; Verträge unverändert; keine neuen produktiven Globals im migrierten
  Bereich; Legacy-Adapter dünn+dokumentiert; kritische Lifecycle-Tests 5× flakefrei; 0 Provider/Skips.
- **Vorbedingung der Umsetzung (historisch, war erfüllt):** Phase-3-Hosted-Runner grün ODER
  ausdrücklicher Verzicht des Nutzers. Erfüllt; Prompt 8 (Phase 4A) ist umgesetzt und gemergt.

## Freigabe

Status **Accepted for incremental implementation** — vom Nutzer am 2026-07-15
ausdrücklich bestätigt. RFC-0001 bleibt unverändert akzeptiert (D1: Root zuerst). Die
Umsetzung (Prompt 8) darf erst nach grünem Phase-3-Hosted-Runner (oder dokumentiertem
Verzicht) beginnen.
