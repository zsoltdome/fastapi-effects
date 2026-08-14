# ADR-006: Runtime recovery provenance

- Status: Accepted
- Date: 2026-08-30

## Decision

Treat commit `6b8d3626445bd577cc6c5af80f3b84e30e2c7712` as the cumulative assurance
baseline. Preserve it on `main` and implement the PostgreSQL runtime as new work.

Milestone 2–6 runtime source was unavailable. We will not fabricate commits, tags, or
release claims to suggest otherwise. `0.6.0a1` remains a pre-alpha assurance release.

Capability documentation uses three states: implemented, reference-only, and planned.
A production capability may move to implemented only when the production adapter—not
only the deterministic reference driver—passes the applicable conformance profile.

## Consequences

The new runtime has an explicit review trail and may choose safer additive details
while preserving Boundary Contract v1. Release and repository gates reject production
claims that still reach `MilestoneNotImplementedError`.
