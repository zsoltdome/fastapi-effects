"""Public target-bound delegation verification entry points."""

from fastapi_mergen.delegation.fastapi import (
    VerifiedDelegation,
    delegated_principal_dependency,
    verified_delegation_dependency,
)
from fastapi_mergen.delegation.signing import DelegationVerifier

__all__ = [
    "DelegationVerifier",
    "VerifiedDelegation",
    "delegated_principal_dependency",
    "verified_delegation_dependency",
]
