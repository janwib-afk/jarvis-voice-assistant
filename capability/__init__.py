"""Capability als tiefes Modul (RFC-0007 + Amendment 1, Variante C).

Drei Verantwortungen hinter einer kleinen Oberflaeche:

* ``_contract``    — Capability Core: **WAS** es gibt (rein, I/O-frei)
* ``_policy``      — Policy Kernel:   **OB** es darf (rein, I/O-frei, total)
* ``_coordinator`` — Coordinator:     **WIE** es ablaeuft (runtime-eigen)
* ``_legacy``      — Adapter ``[ACTION:…]`` -> Capability

Der Import ist vollstaendig I/O-frei: keine Config, kein Netz, keine Uhr, kein
Modul-Global. Die ``Runtime`` besitzt Registry, Regeln und genau einen Coordinator
(§7) — es gibt keinen Service Locator.
"""
from ._contract import (  # noqa: F401
    AUDIT_FIELDS,
    CapabilityContract,
    CapabilityRequest,
    CapabilityView,
    DataClass,
    Decision,
    EffectClass,
    Evidence,
    Health,
    InputSchema,
    Outcome,
    OutcomeStatus,
    OutputSchema,
    Presence,
    Preview,
    Provenance,
    Registry,
    Requirement,
    Retry,
    SchemaError,
    Scope,
    Tier,
    UnknownCapability,
    Verify,
)
from ._policy import (  # noqa: F401
    ACTIVE_RULES,
    DATED_RULES,
    Rule,
    decide,
)
from ._coordinator import (  # noqa: F401
    AttemptContext,
    Cancelled,
    Coordinator,
)
from ._pilots import (  # noqa: F401
    CapabilityDeps,
    build_registry,
    pilot_contracts,
)
from ._legacy import (  # noqa: F401
    MIGRATED_ACTIONS,
    is_migrated,
    run_migrated,
)
from ._ssrf import (  # noqa: F401
    SSRFBlocked,
    TargetGuard,
    Verdict,
    guarded_goto,
    httpx_guarded_get,
    install_page_guard,
)

__all__ = [
    "ACTIVE_RULES", "DATED_RULES", "Rule", "decide",
    "AttemptContext", "Cancelled", "Coordinator",
    "CapabilityDeps", "build_registry", "pilot_contracts",
    "MIGRATED_ACTIONS", "is_migrated", "run_migrated",
    "SSRFBlocked", "TargetGuard", "Verdict",
    "guarded_goto", "httpx_guarded_get", "install_page_guard",
    "AUDIT_FIELDS",
    "CapabilityContract", "CapabilityRequest", "CapabilityView",
    "DataClass", "Decision", "EffectClass", "Evidence", "Health",
    "InputSchema", "Outcome", "OutcomeStatus", "OutputSchema",
    "Presence", "Preview", "Provenance", "Registry", "Requirement",
    "Retry", "SchemaError", "Scope", "Tier", "UnknownCapability", "Verify",
]
