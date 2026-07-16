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

import config_loader
import configuration as configuration_mod

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

    def __init__(self, *, config_path: str, session_token: str,
                 config: dict | None = None, ai=None, http=None):
        self.config_path = config_path
        self.session_token = session_token
        # Einziger Besitzer der Configuration (RFC-0003 D1/D2). Beim Import nur
        # konstruiert — ungeoeffnet, ohne jede I/O; geladen/migriert wird in aopen.
        self.configuration = configuration_mod.Configuration(config_path)
        self.config = config
        self.startup_warnings: list[str] = []
        # Injizierte Clients = BORROWED (nie geschlossen); selbst erzeugte = OWNED.
        self.ai = ai
        self.http = http
        self.owns_ai = ai is None
        self.owns_http = http is None
        # per-App-Laufzeitzustand (Besitz verschoben, Semantik unverändert)
        self.ws_clients: set = set()
        self.conversations: dict = {}
        self.pending_confirm: dict = {}
        # intern
        self._wired = False
        self._refresh_task: "asyncio.Task | None" = None
        self._closed = False

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

        Der Configuration-Snapshot ist die kanonische Wahrheit (RFC-0003 D2);
        ``self.config`` ist bis zum A6-Cleanup nur eine veraenderbare Projektion
        daraus fuer Bestandsleser. Wirft ConfigError (fails-closed) — der Aufrufer
        (Lifespan bzw. `python server.py`) behandelt das.
        """
        snapshot = self.configuration.load()
        self.config = snapshot.as_dict()
        self.startup_warnings = config_loader.check_runtime_environment(self.config)

    def wire(self) -> None:
        """EINZIGER Aufrufer der Start-Verdrahtung (D2), idempotent (_wired):
        memory/assistant_core/app_launcher konfigurieren, Clients injizieren,
        per-App conversations/pending_confirm an die Module aliasen."""
        if self._wired:
            return
        import app_launcher
        import assistant_core
        import memory
        cfg = self.config or {}
        memory.configure(
            vault_path=cfg.get("obsidian_inbox_path", ""),
            inbox_path=cfg.get("obsidian_inbox_folder", ""),
        )
        assistant_core.configure(cfg)
        assistant_core.init_clients(self.ai, self.http)
        # per-App-Session-State: die Modul-Dicts sind ab jetzt DIE Runtime-Dicts
        # (serielle Isolation — Semantik unverändert; RFC-0002 Slice 3).
        assistant_core.conversations = self.conversations
        assistant_core.pending_confirm = self.pending_confirm
        app_launcher.configure(cfg.get("apps", []), cfg.get("launcher"))
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
            import assistant_core
            self._refresh_task = asyncio.create_task(
                asyncio.to_thread(assistant_core.refresh_data))

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
