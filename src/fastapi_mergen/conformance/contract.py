"""Versioned Boundary Contract identifiers and certification profiles."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

CONTRACT_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
SPEC_RESOURCE = "spec/boundary-contract-v1.json"


class Capability(StrEnum):
    """Optional implementation facets understood by the public test kit."""

    TRANSACTIONAL_EFFECTS = "transactional_effects"
    TENANT_ISOLATION = "tenant_isolation"
    AUTHORIZATION = "authorization"
    DELIVERY_LEASES = "delivery_leases"
    CONTEXT_LIFECYCLE = "context_lifecycle"
    WEBHOOKS = "webhooks"
    EXTERNAL_EXECUTOR = "external_executor"
    COMMAND_IDEMPOTENCY = "command_idempotency"
    DELEGATION = "delegation"


class Invariant(StrEnum):
    """Normative invariants exercised by conformance scenarios."""

    ATOMIC_INTENT = "BC-01"
    TENANT_CONTINUITY = "BC-02"
    AUTHORITY_PROVENANCE = "BC-03"
    STABLE_RETRY_IDENTITY = "BC-04"
    INDEPENDENT_FANOUT = "BC-05"
    CAUSAL_LINEAGE = "BC-06"
    REPLAY_ACCOUNTABILITY = "BC-07"
    LEASE_FENCING = "BC-08"
    CONTEXT_CLEANUP = "BC-09"
    SECRET_MINIMIZATION = "BC-10"
    COMMAND_IDENTITY = "BC-11"
    DELEGATION_BINDING = "BC-12"


class CertificationProfile(StrEnum):
    """Named sets of invariants used for stable certification claims."""

    CORE = "core"
    SECURITY = "security"
    DELIVERY = "delivery"
    COMPLETE = "complete"


INVARIANT_CAPABILITIES = MappingProxyType(
    {
        Invariant.ATOMIC_INTENT: frozenset({Capability.TRANSACTIONAL_EFFECTS}),
        Invariant.TENANT_CONTINUITY: frozenset({Capability.TENANT_ISOLATION}),
        Invariant.AUTHORITY_PROVENANCE: frozenset({Capability.AUTHORIZATION}),
        Invariant.STABLE_RETRY_IDENTITY: frozenset({Capability.DELIVERY_LEASES}),
        Invariant.INDEPENDENT_FANOUT: frozenset({Capability.TRANSACTIONAL_EFFECTS}),
        Invariant.CAUSAL_LINEAGE: frozenset({Capability.TRANSACTIONAL_EFFECTS}),
        Invariant.REPLAY_ACCOUNTABILITY: frozenset({Capability.DELIVERY_LEASES}),
        Invariant.LEASE_FENCING: frozenset({Capability.DELIVERY_LEASES}),
        Invariant.CONTEXT_CLEANUP: frozenset({Capability.CONTEXT_LIFECYCLE}),
        Invariant.SECRET_MINIMIZATION: frozenset(),
        Invariant.COMMAND_IDENTITY: frozenset({Capability.COMMAND_IDEMPOTENCY}),
        Invariant.DELEGATION_BINDING: frozenset({Capability.DELEGATION}),
    }
)

PROFILE_INVARIANTS = MappingProxyType(
    {
        CertificationProfile.CORE: frozenset(
            {
                Invariant.ATOMIC_INTENT,
                Invariant.TENANT_CONTINUITY,
                Invariant.AUTHORITY_PROVENANCE,
                Invariant.STABLE_RETRY_IDENTITY,
                Invariant.INDEPENDENT_FANOUT,
                Invariant.CAUSAL_LINEAGE,
                Invariant.REPLAY_ACCOUNTABILITY,
            }
        ),
        CertificationProfile.SECURITY: frozenset(
            {
                Invariant.TENANT_CONTINUITY,
                Invariant.AUTHORITY_PROVENANCE,
                Invariant.LEASE_FENCING,
                Invariant.CONTEXT_CLEANUP,
                Invariant.SECRET_MINIMIZATION,
                Invariant.DELEGATION_BINDING,
            }
        ),
        CertificationProfile.DELIVERY: frozenset(
            {
                Invariant.STABLE_RETRY_IDENTITY,
                Invariant.INDEPENDENT_FANOUT,
                Invariant.REPLAY_ACCOUNTABILITY,
                Invariant.LEASE_FENCING,
            }
        ),
        CertificationProfile.COMPLETE: frozenset(Invariant),
    }
)


def required_capabilities(invariant: Invariant) -> frozenset[Capability]:
    """Return the implementation facets needed to exercise one invariant."""

    return INVARIANT_CAPABILITIES[invariant]


def profile_invariants(profile: CertificationProfile | str) -> frozenset[Invariant]:
    """Parse a profile and return its immutable invariant set."""

    return PROFILE_INVARIANTS[CertificationProfile(profile)]
