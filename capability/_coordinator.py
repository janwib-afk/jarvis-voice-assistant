"""Coordinator — WIE es ablaeuft (RFC-0007 §10/§11/§19/§20, Amendment 1 §A1.6).

``validate -> preview -> authorize -> execute -> verify``. Keine Stufe ist
ueberspringbar; ``execute`` wird nur fuer eine ``Decision`` erreicht, die fuer
**diesen** Versuch berechnet wurde.

Der Coordinator ist **runtime-eigen**, aber besitzt bewusst wenig:

* **kein** Task, **keine** Queue, **kein** Lock — die ``ConversationSession`` behaelt
  Turn-, Queue- und Cancel-Besitz (RFC-0006).
* **keine** Retry-Schleife — ``retry`` ist deklarative Eignung, keine Engine (§19).
* **kein** Ergebnis-Cache und **keine** automatische Deduplizierung; der
  Idempotency Key wird erzeugt und **uebergeben**, nicht ausgewertet (Amendment F4).

**Cancellation ist die ausdrueckliche Ausnahme von "verify laeuft immer"**
(Amendment F2): eine ``asyncio.CancelledError`` wird sofort und unveraendert
weitergereicht — kein ``finally`` haelt sie auf, kein Verify, kein Audit-Await.
Der Ausgang ``cancelled`` bezeichnet demgegenueber **nur** eine vom Executor normal
gemeldete kooperative Domaenenstornierung (Amendment F3).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

import obslog

from ._contract import (
    CapabilityContract,
    CapabilityRequest,
    Evidence,
    Outcome,
    OutcomeStatus,
    Preview,
    Registry,
    Verify,
)
from ._policy import ACTIVE_RULES, decide


@dataclass(frozen=True)
class Cancelled:
    """Vom Executor gemeldete **kooperative** Domaenenstornierung (Amendment F3).

    Ausdruecklich NICHT dasselbe wie eine propagierte ``asyncio.CancelledError``:
    diese verlaesst den Coordinator als Exception und erzeugt gar kein ``Outcome``.
    """
    reason: str = ""


@dataclass(frozen=True)
class AttemptContext:
    """Was die Ausfuehrung vom Coordinator bekommt — bewusst wenig.

    ``meta`` traegt **opake Transport-Metadaten** (z.B. die Wire-Correlation eines
    REST-Requests fuer einen nachgelagerten Broadcast). Sie ist **kein** Capability-
    Eingabefeld: sie geht NICHT in Validierung oder Idempotency Key ein (§18/§19 —
    ``correlation_id`` ist keine Job-ID, ``event_id`` kein Idempotency Key).
    """
    capability: str
    version: int
    idempotency_key: str
    preview_hash: str | None
    deps: Any = None
    meta: Mapping[str, Any] | None = None


def _canonical(payload: Mapping[str, Any]) -> str:
    """Stabile Serialisierung fuer Preview-Hash und Idempotency Key."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class Coordinator:
    """Runtime-eigen. Genau eine Instanz je ``Runtime`` (§7) — kein Service Locator."""

    def __init__(self, registry: Registry, rules=ACTIVE_RULES, *,
                 clock=time.monotonic, audit=obslog.event,
                 dedupe_scope: str = "runtime", deps: Any = None):
        self._registry = registry
        self._rules = tuple(rules)
        self._clock = clock
        self._audit = audit
        self._dedupe_scope = dedupe_scope
        self._deps = deps

    # ── passiv, kostenfrei (§20) ────────────────────────────────────────────

    def inspect(self, name: str | None = None):
        return self._registry.inspect(name)

    def health(self) -> dict:
        """Liest Registry und Regelnamen — mehr nicht. Keine Providerkosten."""
        return {
            "capabilities": len(self._registry),
            "rules": tuple(r.name for r in self._rules),
        }

    def idempotency_key(self, request: CapabilityRequest) -> str:
        """Deterministisch aus (Name, Version, kanonischer Eingabe, Dedupe-Scope).

        Wire-IDs sind als Parameter **nicht annehmbar**: sie sind keine
        Schemafelder und scheitern schon an der Validierung (§18/§19).
        """
        contract = self._registry.get(request.capability)
        canonical = _canonical(contract.inputs.validate(request.payload))
        raw = "\x1f".join((contract.name, str(contract.version),
                           canonical, self._dedupe_scope))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── der Lifecycle ───────────────────────────────────────────────────────

    async def attempt(self, request: CapabilityRequest,
                      evidence: Evidence | None = None, *,
                      meta: Mapping[str, Any] | None = None) -> Outcome:
        evidence = evidence or Evidence()

        # 1) validate — ein Adapter, der Unsinn schickt, bekommt kein Outcome (§11).
        contract = self._registry.get(request.capability)
        payload = contract.inputs.validate(request.payload)

        # 2) preview — kanonisch aus der EINGEFRORENEN Eingabe. Weil ``payload``
        #    unveraenderlich ist, kann sich der Hash zwischen Entscheidung und
        #    Ausfuehrung strukturell nicht aendern; TOCTOU ist hier nicht
        #    darstellbar statt nur unwahrscheinlich.
        preview_hash = None
        if contract.preview is not Preview.NONE:
            preview_hash = hashlib.sha256(
                _canonical(payload).encode("utf-8")).hexdigest()

        # 3) authorize — genau eine Entscheidung fuer genau diesen Versuch.
        decision = decide(contract, request, evidence, self._rules)
        if decision.denials:
            return self._finish(contract, OutcomeStatus.DENIED, None,
                                denials=decision.denials, duration_ms=0)
        if decision.requirements:
            return self._finish(contract, OutcomeStatus.NEEDS, None,
                                requirements=decision.requirements, duration_ms=0)

        # 4) execute — genau ein Timeout-Owner (Amendment F1), kein Retry (§19).
        ctx = AttemptContext(
            capability=contract.name, version=contract.version,
            idempotency_key=self.idempotency_key(request),
            preview_hash=preview_hash, deps=self._deps, meta=meta,
        )
        started = self._clock()
        try:
            result = await asyncio.wait_for(
                contract.execute(payload, ctx), timeout=contract.timeout_s)
        except asyncio.CancelledError:
            # Sofort und unveraendert weiter. Kein Verify, kein Audit, kein
            # finally — nichts darf den Abbruch aufhalten (Amendment F2).
            raise
        except asyncio.TimeoutError:
            return self._finish(contract, OutcomeStatus.TIMEOUT, None,
                                duration_ms=self._ms(started))
        except Exception as e:
            # Nur der Typ verlaesst den Coordinator — nie die Meldung (SI-9).
            return self._finish(contract, OutcomeStatus.FAILED, None,
                                error_type=type(e).__name__,
                                duration_ms=self._ms(started))

        # 5) verify — darf ``ok`` zu ``partial`` herabstufen, nie umgekehrt (§11).
        duration_ms = self._ms(started)
        if isinstance(result, Cancelled):
            return self._finish(contract, OutcomeStatus.CANCELLED, None,
                                duration_ms=duration_ms)
        if contract.verify is Verify.NONE:
            # Statt Erfolg zu behaupten, wird der Umstand vermerkt (§10/§20).
            self._audit("capability.unverified", capability=contract.name,
                        version=contract.version)
            return self._finish(contract, OutcomeStatus.OK, result,
                                duration_ms=duration_ms)
        value, missing = self._verified(contract, result)
        if missing:
            return self._finish(contract, OutcomeStatus.PARTIAL, value,
                                pending=missing, duration_ms=duration_ms)
        return self._finish(contract, OutcomeStatus.OK, value,
                            duration_ms=duration_ms)

    # ── intern ──────────────────────────────────────────────────────────────

    def _ms(self, started: float) -> int:
        return int((self._clock() - started) * 1000)

    @staticmethod
    def _verified(contract: CapabilityContract, result):
        """Beobachtbare Evidenz gegen das deklarierte Ergebnisschema."""
        if not isinstance(result, Mapping):
            return {}, tuple(contract.output.fields)
        missing = tuple(f for f in contract.output.fields if f not in result)
        return {f: result[f] for f in contract.output.fields if f in result}, missing

    def _finish(self, contract, status, value, *, denials=frozenset(),
                requirements=frozenset(), error_type=None, pending=(),
                duration_ms=0) -> Outcome:
        # Audit: ausschliesslich Allowlist-Metadaten. Payloads, Inhalte, URLs und
        # Preview-Hashes sind hier strukturell nicht nennbar (Amendment F5).
        self._audit("capability.attempted",
                    capability=contract.name, version=contract.version,
                    outcome=status.value, duration_ms=duration_ms,
                    effects="/".join(sorted(e.value for e in contract.effects)))
        return Outcome(status=status, value=value, denials=denials,
                       requirements=requirements, error_type=error_type,
                       pending=pending)
