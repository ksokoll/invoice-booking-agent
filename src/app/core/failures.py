"""Verification failure types and routing classifications.

The Hard/Consultable distinction is the routing key used by the
Coordinator to decide whether a failure is terminal or whether it
opens a recovery path through a correspondent (Procurement).
Each VerificationFailure declares its own consultability at the
point of construction; the Coordinator inspects the field directly.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationFailure:
    """Describes a contradiction or rule violation found during verification.

    Attributes:
        rule: Identifier of the rule that failed.
        reason: Human-readable explanation of the contradiction.
        consultable: True if the failure may be recoverable through a
            consultation with Procurement; False if it is terminal.
    """

    rule: str
    reason: str
    consultable: bool
