"""Verification failure types and routing classifications.

The Hard/Consultable distinction is the routing key used by the
Coordinator to decide whether a failure is terminal or whether it
opens a recovery path through a correspondent (Procurement).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationFailure:
    """Describes a contradiction or rule violation found during verification.

    Attributes:
        rule: Identifier of the rule that failed.
        reason: Human-readable explanation of the contradiction.
    """

    rule: str
    reason: str


# Failure rules that can be recovered through consultation with
# Procurement. Every other failure rule is treated as hard and
# terminates the Coordinator loop immediately.
CONSULTABLE_RULES: frozenset[str] = frozenset(
    {
        "limit_not_exceeded",
        "budget_sufficient",
    }
)
