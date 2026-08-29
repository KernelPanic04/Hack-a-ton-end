"""Declarative action policy for runtime decisions."""

# Keep this package lightweight: the optional coordinator imports the runtime
# pipeline, while WS actions import the policy engine during app startup.
from app.policy.engine import ActionPolicyEngine, PolicyViolation

__all__ = ["ActionPolicyEngine", "PolicyViolation"]
