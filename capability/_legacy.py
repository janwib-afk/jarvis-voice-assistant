"""Legacy-Adapter: ``[ACTION:…]`` -> Capability (RFC-0007 §22, Amendment 1 §A1.1).

Bildet **migrierte** Actions auf Capability-Requests ab und projiziert das ``Outcome``
zurueck auf den rohen Ergebnis-String, den ``assistant_core.run_action_and_respond``
erwartet. Das ``[ACTION:…]``-Wire-Format und ``ActionSpec`` bleiben unveraendert
(RFC-0001 bleibt bindend); der Prompt und die Selbstbeschreibung aendern sich nicht.

In der **Pilotphase** ist genau eine Voice-Action migriert: ``SEARCH`` -> ``web.search``.
Die uebrigen 20 Actions laufen unveraendert ueber ``execute_action`` (Prompt 20,
Amendment 1 §A1.1).

``execute`` importiert ``browser_tools`` **lazy**, damit ``import capability`` I/O-frei
und leicht bleibt.
"""
from __future__ import annotations

from ._contract import (
    CapabilityContract,
    CapabilityRequest,
    DataClass,
    EffectClass,
    Evidence,
    Health,
    InputSchema,
    OutcomeStatus,
    OutputSchema,
    Preview,
    Provenance,
    Retry,
    Scope,
    Verify,
)

#: ActionSpec.type -> stabiler Capability-Name der migrierten Piloten.
MIGRATED_ACTIONS: dict[str, str] = {"SEARCH": "web.search"}


def is_migrated(action_type: str) -> bool:
    return action_type in MIGRATED_ACTIONS


async def _exec_web_search(payload, ctx):
    """Deckungsgleich mit ``actions._exec_search``: byte-identisches rohes Ergebnis."""
    import browser_tools
    result = await browser_tools.search_and_read(payload["query"])
    if "error" not in result:
        text = (f"Seite: {result.get('title', '')}\nURL: {result.get('url', '')}"
                f"\n\n{result.get('content', '')[:2000]}")
    else:
        text = f"Suche fehlgeschlagen: {result.get('error', '')}"
    return {"text": text}


def web_search_contract(deps=None) -> CapabilityContract:
    """Der Pilot-Vertrag fuer ``SEARCH``. Version 1 (Amendment 1 §A1.7 G1)."""
    return CapabilityContract(
        name="web.search", version=1, title="Websuche",
        inputs=InputSchema(fields=("query",)),
        output=OutputSchema(fields=("text",)),
        # Folgeeffekte vollstaendig deklariert (Amendment 1 §A1.2): Suche, Summary-LLM
        # und TTS sind network-read; der sichtbare Chromium-Prozess und der
        # PowerShell-SetForegroundWindow-Fokus sind local-execute.
        effects=(EffectClass.NETWORK_READ, EffectClass.LOCAL_EXECUTE),
        reads=(DataClass.PUBLIC,), writes=(),
        scopes=(Scope.WEB,),
        timeout_s=60,  # identisch zu ActionSpec("SEARCH").timeout (Default 60)
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={"query": "wetter"},
        execute=_exec_web_search,
    )


async def run_migrated(coordinator, action, ctx) -> str:
    """Eine migrierte Action ueber den Coordinator fuehren; ``Outcome`` -> roher String.

    Provenance ist **derived**: ein ``[ACTION:…]`` stammt aus der LLM-Antwort — zwischen
    Nutzer und Tag liegt das Modell (§14). Der Coordinator ist der **einzige**
    Timeout-Owner dieses Pfades (Amendment 1 §A1.6 F1): hier gibt es kein zweites
    ``asyncio.wait_for``.
    """
    name = MIGRATED_ACTIONS[action.type]
    request = CapabilityRequest(name, Provenance.DERIVED, {"query": action.payload})
    # web.search-Ziel ist der FESTE Suchmaschinen-Host (nicht nutzergesteuert). Die
    # SSRF-Durchsetzung auf JEDE tatsaechliche Navigation inkl. Ergebnis-Klick und
    # Redirect ist Slice 6 (Playwright-Transportguard) — hier noch NICHT geschuetzt.
    evidence = Evidence(target_allowed=True)
    outcome = await coordinator.attempt(request, evidence)
    if outcome.status is OutcomeStatus.OK:
        return outcome.value["text"]
    if outcome.status is OutcomeStatus.TIMEOUT:
        return "Suche fehlgeschlagen: Zeitüberschreitung."
    # denied/needs/failed/partial: dieselbe sprechbare Fehlerform wie der Alt-Pfad.
    return "Suche fehlgeschlagen: nicht ausführbar."
