# Boundary conformance and assurance

Milestone 7 turns the Mergen Boundary Contract into an executable certification kit.
The suite is transport- and storage-neutral: a system under test implements narrow
facet protocols, declares its capabilities, and is exercised through deterministic
scenarios.

## Purpose

The assurance layer answers concrete questions that ordinary unit coverage does not:

- Did a rollback leave any event or delivery intent behind?
- Can a tenant principal observe another tenant's boundary state?
- Can revalidation introduce authority absent from the original operation?
- Does an automatic retry change the consumer-visible identity?
- Can a stale worker finalize after another worker has reclaimed a lease?
- Does principal context survive into the next tenant's job?
- Does a duplicate command execute twice under concurrency?
- Can a delegated credential be reused for another audience or route?
- Does a webhook sign bytes other than the exact body sent, or accept a private IP?
- Is broker enqueue incorrectly treated as terminal handler success?
- Can a duplicate broker message execute the same handoff twice?
- Do public evidence files expose a configured secret canary?

## Architecture

```text
trusted adapter factory
        │
        ▼
CapabilityManifest ──SHA-256──┐
        │                      │
        ▼                      ▼
facet protocols       ConformanceRunner
                              │
                 deterministic scenarios
                              │
                 bounded CheckResult values
                              │
                    ConformanceReport
                    │      │      │
                  JSON   JUnit   SARIF / Markdown
                    │
            independent verification
```

The in-memory `ReferenceBoundaryDriver` is a specification oracle, not a production
store. It implements every facet and supports one intentional fault for each major
failure mode. The release audit requires all profiles to pass without faults and
requires every fault to prevent complete certification.

## Profiles and claims

A report may claim only the selected profile. A complete profile is not inferred from
an adapter name or from package version. The profile's invariant coverage is derived
from runtime contract data, and archived reports are checked again during parsing.

A report is **not certified** when any required invariant is missing, failed, skipped,
or errored. An empty or partial report cannot become certified by setting a Boolean
field in JSON; derived status, counts, certification, and digest are re-computed.

## Driver protocols

The minimum driver lifecycle is:

```python
class BoundaryDriver(Protocol):
    @property
    def manifest(self) -> CapabilityManifest: ...
    async def reset(self) -> None: ...
    async def close(self) -> None: ...
    async def public_evidence(self) -> Mapping[str, object]: ...
```

Capability facets then expose transaction publication, tenant snapshots, delivery
claims, authorization resolution, context lifecycle, transactional command identity,
delegation, signed webhook delivery, and external-executor handoff. An adapter should
call the real implementation path rather than replicate expected answers in a mock.

## Failure behavior

Each scenario and driver cleanup has an independent bounded timeout. Assertion
failures become `fail`; unexpected exception types become `error` without copying the
exception message. Unsupported profile invariants become `skip`, which also prevents
certification. Driver cleanup is always attempted; timeout or failure produces a
critical error.

## Secret canaries

The built-in secret-minimization scenario checks known reference canaries. A deployment
can additionally supply environment-variable names:

```bash
fastapi-mergen conformance run \
  --adapter myapp.mergen_conformance:create_driver \
  --profile complete \
  --secret-canary-env DATABASE_PASSWORD \
  --secret-canary-env WEBHOOK_MASTER_KEY
```

Only the environment-variable values are compared against non-published audit
material. The names and values are not added to the report. Command-line literal
secrets are intentionally unsupported because process listings and shell history are
not safe secret channels.

## What certification does not prove

The suite does not provide formal verification, authenticate the adapter author,
prove production configuration parity, inspect a hidden database role, or make a
remote effect exactly once. It provides repeatable evidence that the tested boundary
adapter preserved the declared contract under the published scenarios.
