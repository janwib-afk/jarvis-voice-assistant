"""Composition Root — Runtime: Besitz + Lifecycle von Config, Clients, per-App-State.

RFC-0002 (+ Amendment 1, voll-lazy Import): Der Import erzeugt nur eine
**ungeöffnete** Runtime (`config_path` aufgelöst + `session_token` erzeugt, keine
I/O). Config und OWNED-Clients (`ai`/`http`) entstehen **ausschließlich** im
FastAPI-Lifespan (`aopen`) und werden dort deterministisch geschlossen (`aclose`).

Ownership (D3): selbst erzeugte Clients sind OWNED (im Lifespan geschlossen);
von außen injizierte Clients (Tests) sind BORROWED (nie geschlossen). Der Root ist
der einzige Aufrufer der `configure()`-Startverdrahtung (D2); Settings-Live-Apply
(Kandidat 05) bleibt außerhalb.
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import secrets
from contextlib import asynccontextmanager

import anthropic
import httpx

import capability
import config_loader
import configuration as configuration_mod
import conversation
import wire_protocol

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


async def _aclose_client(client) -> None:
    """Client SDK-nativ schließen (aclose bevorzugt, sonst close); tolerant."""
    for name in ("aclose", "close"):
        fn = getattr(client, name, None)
        if fn is None:
            continue
        result = fn()
        if inspect.isawaitable(result):
            await result
        return


class Runtime:
    """Eindeutiger Besitzer von Config, Clients, Browser-Lifecycle und per-App-State.

    Beim Import wird nur eine ungeöffnete Instanz erzeugt (keine Config/Clients).
    """

    def __init__(self, *, config_path: str, session_token: str, ai=None, http=None):
        self.config_path = config_path
        self.session_token = session_token
        # Einziger Besitzer der Configuration (RFC-0003 D1/D2). Beim Import nur
        # konstruiert — ungeoeffnet, ohne jede I/O; geladen/migriert wird in aopen.
        self.configuration = configuration_mod.Configuration(config_path)
        self.startup_warnings: list[str] = []
        # Injizierte Clients = BORROWED (nie geschlossen); selbst erzeugte = OWNED.
        self.ai = ai
        self.http = http
        self.owns_ai = ai is None
        self.owns_http = http is None
        # per-App-Laufzeitzustand (Besitz verschoben, Semantik unverändert)
        self.ws_clients: set = set()
        # Wire-Protokoll + Verbindungsregistry (RFC-0005 §12): runtime-besessen,
        # kein Modul-Global. Import-sicher (kein I/O). Legacy bleibt Default.
        self.wire_protocol = wire_protocol.WireProtocol()
        self.connections = wire_protocol.ConnectionRegistry(self.wire_protocol)
        # Conversation-Zustand (RFC-0006 D4): genau EIN runtime-eigener Manager,
        # der alle Sessions besitzt. Konstruktion ist I/O-frei (Import-Sicherheit).
        self.conversation_manager = conversation.ConversationManager()
        # Capability-/Policy-Kernel (RFC-0007 §7): genau EIN runtime-eigener
        # Coordinator ueber der eingefrorenen Pilot-Registry und den aktiven Regeln.
        # Konstruktion ist I/O-frei; der Dedupe-Scope ist an diese App gebunden
        # (§19). Kein Modul-Global, kein Service Locator — deps ist eine konkrete
        # Objektreferenz auf diese Runtime (§7).
        # SSRF-TargetGuard (RFC-0007 §21): genau EIN Guard, den Coordinator-Deps und
        # browser_tools teilen. Konstruktion ist I/O-frei (nur der Resolver wird
        # gehalten); die Injektion in browser_tools passiert in wire().
        self._target_guard = capability.TargetGuard()
        _cap_deps = capability.CapabilityDeps(runtime=self, target_guard=self._target_guard)
        self.capabilities = capability.Coordinator(
            capability.build_registry(_cap_deps),
            capability.ACTIVE_RULES,
            dedupe_scope=session_token,
            deps=_cap_deps,
        )
        # Launcher-Persist-Adapter (RFC-0007 §17, Slice 8): der Server injiziert seine
        # ``persist_launcher_intent``-Orchestrierung (configuration.mutate als einziger
        # Writer + Live-Apply + Broadcast). Explizite Instanz-Injektion, kein
        # Modul-Global, kein Service Locator; der Kernel/Coordinator kann so eine
        # REST-Wirkung ausfuehren, ohne dass ``capability`` ``server`` importiert.
        self._launcher_persist = None
        # intern
        self._wired = False
        self._refresh_task: "asyncio.Task | None" = None
        self._closed = False

    def configure_launcher_persist(self, fn) -> None:
        """Vom Server (``create_app``) gesetzte Persist-Orchestrierung."""
        self._launcher_persist = fn

    def apply_document(self, merged: dict) -> bool:
        """NOTWENDIGES Live-Apply (RFC-0003 D9): deterministisch, ohne Netz/Broadcast.

        Laeuft INNERHALB der Transaktion — wirft es, stellt der Writer Datei und
        Snapshot wieder her. Gibt zurueck, ob ein Post-Commit-Refresh noetig ist.
        """
        import app_launcher
        import assistant_core
        import config_loader
        import memory
        needs_refresh = (
            merged.get("city", assistant_core.CITY) != assistant_core.CITY
            or merged.get("obsidian_inbox_path", memory.VAULT_PATH) != memory.VAULT_PATH
            or merged.get("obsidian_inbox_folder", memory.INBOX_PATH) != memory.INBOX_PATH
        )
        assistant_core.configure(merged)
        memory.configure(
            vault_path=merged.get("obsidian_inbox_path", ""),
            inbox_path=merged.get("obsidian_inbox_folder", ""),
        )
        app_launcher.configure(merged.get("apps", []), merged.get("launcher"))
        self.startup_warnings = config_loader.check_runtime_environment(merged)
        return needs_refresh

    async def persist_launcher(self, intent, kind: str, correlation_id=None) -> list[str]:
        """Semantische Launcher-Mutation ueber den EINZIGEN Writer (RFC-0003).

        Delegiert an die injizierte Server-Orchestrierung; ohne Injektion ein Fehler
        (fail-closed) statt einer stillen Umgehung."""
        if self._launcher_persist is None:
            raise RuntimeError("launcher persist nicht konfiguriert")
        return await self._launcher_persist(self, intent, kind, correlation_id)

    async def refresh_context(self):
        """Kontextdaten (Wetter + Vault-Scan) ueber den Coordinator neu laden.

        Startup und Post-Settings-Save nutzen denselben Pfad (RFC-0007 Slice 9). Kein
        Nutzerausloeser (§2.6.3); der Coordinator ist der Timeout-Owner. Gibt das
        ``Outcome`` zurueck — der Aufrufer entscheidet ueber Degraded/Ignorieren."""
        return await self.capabilities.attempt(
            capability.CapabilityRequest(
                "context.refresh", capability.Provenance.OPERATOR, {}),
            capability.Evidence(target_allowed=True))

    @property
    def config(self) -> dict | None:
        """Read-only/defensive Projektion des aktuellen Configuration-Snapshots.

        Bewusst KEINE zweite veraenderbare Wahrheit (RFC-0003 D2): jeder Zugriff
        leitet frisch aus dem kanonischen Snapshot ab und liefert eine tiefe
        Kopie — eine Aenderung daran trifft den Kern nie und kann nicht veralten.
        ``None``, solange die Configuration nicht geladen ist (Import-Sicherheit).
        Kompatibilitaetszugriff fuer Bestandsleser (wire/aopen).
        """
        if self.configuration._snapshot is None:
            return None
        return self.configuration.snapshot().as_dict()

    @property
    def owns_clients(self) -> bool:
        return self.owns_ai or self.owns_http

    @classmethod
    def for_production(cls, config_path: str | None = None, *, environ=None,
                       ai=None, http=None) -> "Runtime":
        """Import-sicher: nur Pfad auflösen + Token erzeugen. KEINE Config-I/O,
        KEIN Client, KEIN sys.exit."""
        environ = os.environ if environ is None else environ
        path = config_loader.resolve_config_path(environ, config_path or _DEFAULT_CONFIG_PATH)
        return cls(config_path=path, session_token=secrets.token_urlsafe(24), ai=ai, http=http)

    def load_config(self) -> None:
        """Configuration laden + ggf. v0→v1 migrieren + Warnungen ermitteln.

        Der Configuration-Snapshot ist die EINZIGE kanonische Wahrheit (RFC-0003
        D2); ``self.config`` ist nur eine read-only Projektion daraus. Wirft
        ConfigError (fails-closed) — der Aufrufer (Lifespan bzw. `python
        server.py`) behandelt das.
        """
        snapshot = self.configuration.load()
        self.startup_warnings = config_loader.check_runtime_environment(snapshot.as_dict())

    def wire(self) -> None:
        """EINZIGER Aufrufer der Start-Verdrahtung (D2), idempotent (_wired):
        memory/assistant_core/app_launcher konfigurieren, Clients injizieren,
        Clients injizieren. Session-Zustand liegt seit RFC-0006 im Manager."""
        if self._wired:
            return
        import app_launcher
        import assistant_core
        import browser_tools
        import memory
        cfg = self.config or {}
        memory.configure(
            vault_path=cfg.get("obsidian_inbox_path", ""),
            inbox_path=cfg.get("obsidian_inbox_folder", ""),
        )
        assistant_core.configure(cfg)
        assistant_core.init_clients(self.ai, self.http)
        app_launcher.configure(cfg.get("apps", []), cfg.get("launcher"))
        # Denselben SSRF-Guard in die Browsersteuerung injizieren (RFC-0007 §21).
        browser_tools.configure_guard(self._target_guard)
        self._wired = True

    async def aopen(self) -> None:
        """Lifespan-Start: Config laden (falls nötig), OWNED-Clients erzeugen,
        verdrahten, Refresh-Task starten. Fehler propagieren (fails-closed)."""
        if self.config is None:
            self.load_config()
        if self.owns_http and self.http is None:
            self.http = httpx.AsyncClient(timeout=30)
        if self.owns_ai and self.ai is None:
            self.ai = anthropic.AsyncAnthropic(
                api_key=self.config["anthropic_api_key"], timeout=30.0, max_retries=2)
        self.wire()
        if not os.environ.get("JARVIS_SKIP_STARTUP_REFRESH"):
            # Startup-Refresh ueber die context.refresh-Capability (RFC-0007 Slice 9):
            # weiterhin fire-and-forget (ein Fehler wird zum FAILED-Outcome und crasht
            # den Startup nicht). Kein zusaetzlicher Aufruf — derselbe eine Refresh.
            self._refresh_task = asyncio.create_task(self.refresh_context())

    async def aclose(self) -> None:
        """Lifespan-Shutdown: idempotent, partial-failure-fest. Refresh-Task
        canceln, Browser schließen, OWNED-Clients schließen (BORROWED nie)."""
        if self._closed:
            return
        self._closed = True
        task = self._refresh_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._refresh_task = None
        # Aktive Conversation Sessions VOR den abhaengigen Ressourcen schliessen
        # (RFC-0006 Paragraph 8): kein Turn laeuft noch, wenn Browser/Clients gehen.
        with contextlib.suppress(Exception):
            await self.conversation_manager.aclose()
        import browser_tools
        with contextlib.suppress(Exception):
            await browser_tools.close()
        if self.owns_http and self.http is not None:
            with contextlib.suppress(Exception):
                await _aclose_client(self.http)
        if self.owns_ai and self.ai is not None:
            with contextlib.suppress(Exception):
                await _aclose_client(self.ai)

    @asynccontextmanager
    async def lifespan(self, app):
        try:
            await self.aopen()
        except BaseException:
            # Partial-Failure: bereits geöffnete OWNED-Ressourcen schließen,
            # bevor der Startup-Fehler weitergereicht wird (kein Leak).
            await self.aclose()
            raise
        try:
            yield
        finally:
            await self.aclose()
