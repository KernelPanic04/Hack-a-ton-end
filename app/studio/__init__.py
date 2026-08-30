"""Freeform, prompt-driven UI generation, decoupled from the run engine.

Unlike ``app/synthesis``, nothing here is tied to a ``RunProjection`` or a
policy-authorized action: a prompt goes in, a validated UI layout comes out.
The backend only produces this JSON; rendering it is the frontend's job.
"""

from app.studio.llm import StudioUIGenerator
from app.studio.schema import StudioUISpec

__all__ = ["StudioUIGenerator", "StudioUISpec"]
