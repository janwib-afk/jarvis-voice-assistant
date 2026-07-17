"""Injizierbare Clock-/ID-Seams (RFC-0005 §23) — deterministische Tests."""
from __future__ import annotations

import datetime
import time
import uuid


class SystemClock:
    """Produktiv: RFC3339 UTC mit Millisekunden (D7)."""

    def now_iso(self) -> str:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    def now_epoch(self) -> float:
        return time.time()


class FixedClock:
    """Test-Seam: fester Zeitstempel."""

    def __init__(self, value: str, epoch: float = 1_700_000_000.0) -> None:
        self._value = value
        self._epoch = epoch

    def now_iso(self) -> str:
        return self._value

    def now_epoch(self) -> float:
        return self._epoch


class UuidGen:
    """Produktiv: kanonische UUIDv4 (A1.B)."""

    def new_id(self) -> str:
        return str(uuid.uuid4())


class SequenceIdGen:
    """Test-Seam: feste ID-Folge."""

    def __init__(self, ids) -> None:
        self._ids = list(ids)
        self._i = 0

    def new_id(self) -> str:
        if self._i >= len(self._ids):
            raise AssertionError("SequenceIdGen erschoepft — mehr Events als IDs")
        v = self._ids[self._i]
        self._i += 1
        return v
