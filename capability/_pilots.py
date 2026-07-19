"""Pilot-Registry und Abhaengigkeiten (RFC-0007 Amendment 1, Pilotphase).

Diese Datei versammelt die **vier** Pilot-Vertraege der Pilotphase und baut daraus
die runtime-eigene Registry. In der Pilotphase waechst die Liste Slice fuer Slice:
Slice 5 (`web.search`), 7 (`memory.forget`), 8 (`launcher.profile.rename`),
9 (`context.refresh`). Die verbleibenden 20 Actions und neun REST-Routen folgen erst
in Prompt 20 (Amendment 1 §A1.1).

Import-frei von I/O: ``build_registry`` konstruiert nur Vertraege (kein Netz, keine
Datei, keine Uhr).
"""
from __future__ import annotations

from dataclasses import dataclass

from ._contract import Registry


@dataclass(frozen=True)
class CapabilityDeps:
    """Explizite Abhaengigkeiten der Pilot-Executor.

    **Kein Service Locator** (§7): eine konkrete Objektreferenz auf die Runtime, kein
    globaler String-Lookup. Der Executor eines Piloten liest daraus genau, was er
    braucht — der ``target_guard`` kommt in Slice 6 hinzu, die Runtime traegt
    ``http``/``configuration`` fuer die spaeteren Piloten.
    """
    runtime: object = None
    target_guard: object = None


def pilot_contracts(deps: CapabilityDeps) -> list:
    """Die Pilot-Vertraege dieser Phase. Waechst Slice fuer Slice (5/7/8/9)."""
    from . import _legacy
    contracts: list = [
        _legacy.web_search_contract(deps),               # Slice 5
        _legacy.memory_forget_contract(deps),            # Slice 7
        _legacy.launcher_profile_rename_contract(deps),  # Slice 8
        _legacy.context_refresh_contract(deps),          # Slice 9
        # ── Phase 5C (Prompt 20) ────────────────────────────────────────────
        _legacy.launcher_profile_status_contract(deps),   # 5C Slice 1
        _legacy.conversation_summary_contract(deps),      # 5C Slice 1
        _legacy.web_browse_contract(deps),                # 5C Slice 3
        _legacy.web_open_contract(deps),                  # 5C Slice 3
        _legacy.web_news_contract(deps),                  # 5C Slice 3
        _legacy.web_research_contract(deps),              # 5C Slice 3
        _legacy.vault_inbox_read_contract(deps),          # 5C Slice 4
        _legacy.memory_read_contract(deps),               # 5C Slice 4
        _legacy.vault_notes_recent_contract(deps),        # 5C Slice 4
        _legacy.vault_project_context_contract(deps),     # 5C Slice 4
        _legacy.vault_inbox_write_contract(deps),         # 5C Slice 5
        _legacy.memory_write_contract(deps),              # 5C Slice 5
        _legacy.clipboard_note_contract(deps),            # 5C Slice 5
        _legacy.clipboard_process_contract(deps),         # 5C Slice 6
        _legacy.screen_describe_contract(deps),           # 5C Slice 6
        _legacy.launcher_app_open_contract(deps),         # 5C Slice 7
        _legacy.launcher_profile_activate_contract(deps), # 5C Slice 7
        _legacy.launcher_autostart_set_contract(deps),    # 5C Slice 7
        _legacy.launcher_placement_set_contract(deps),    # 5C Slice 7
    ]
    return contracts


def build_registry(deps: CapabilityDeps | None = None) -> Registry:
    """Baut die eingefrorene Pilot-Registry (I/O-frei)."""
    return Registry(pilot_contracts(deps or CapabilityDeps()))
