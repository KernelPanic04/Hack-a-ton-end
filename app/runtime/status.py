"""Persistence-only run statuses.

These values describe the SQL row and are intentionally separate from the
public ``RunProjection.status`` contract. A decision-required row is exposed as
``paused`` and an internal error is exposed as ``failed`` on the wire.
"""

from enum import Enum


class StoredRunStatus(str, Enum):
    RUNNING = "running"
    DECISION_REQUIRED = "decision_required"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
