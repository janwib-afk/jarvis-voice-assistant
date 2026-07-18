"""Conversation als tiefes Modul (RFC-0006 + Amendment 1).

Kleine oeffentliche Oberflaeche (§24): der reine Transitionskern plus — ab Slice 3 —
der runtime-eigene Manager. Codec/Transport bleiben bei RFC-0005
(``wire_protocol``); dieses Modul besitzt Conversation-Zustand, nicht den Codec.

Import ist vollstaendig I/O-frei.
"""
from ._core import (  # noqa: F401
    # Zustand
    SessionState,
    Suspended,
    Turn,
    initial_session_state,
    step,
    # Ereignisse
    ConfirmationOpened,
    Disconnected,
    ExecutionEnded,
    SayTextReceived,
    StopReceived,
    TurnFailed,
    TurnFinished,
    # Effekte
    CancelActive,
    CloseSession,
    EmitStopAck,
    EmitStopped,
    StartTurn,
)
from ._session import (  # noqa: F401
    STOPPED_TEXT,
    ConversationManager,
    ConversationSession,
)

__all__ = [
    "SessionState", "Suspended", "Turn", "initial_session_state", "step",
    "ConfirmationOpened", "Disconnected", "ExecutionEnded", "SayTextReceived",
    "StopReceived", "TurnFailed", "TurnFinished",
    "CancelActive", "CloseSession", "EmitStopAck", "EmitStopped", "StartTurn",
    "ConversationManager", "ConversationSession", "STOPPED_TEXT",
]
