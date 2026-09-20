# 2026-09-20 remediation recheck

This clean record tracks the actionable findings from the internal review checklist
without promoting a dirty working tree to committed, hosted, external, or released
evidence. The reviewed checklist has SHA-256
`40ee40ab7326914551130722bf4031b64624648cfc77d2b4f78213581b5d98d0`; remediation
started from repository commit `06d63b701daab26bf00909a5c7150c0ed097ef3c`.

[`recheck-results.json`](recheck-results.json) is the machine-readable local execution
record. It deliberately sets `release_evidence_authority` to false. Generated files
under `build/release/` and `dist/` are local diagnostics, not protected-workflow
artifacts, and the base commit does not identify the uncommitted remediation.

## Implemented source boundaries

- **F01:** an empty eligible signing-key lookup is a delivery-local permanent failure;
  master-key, decryption, and database configuration failures still escape. A real
  `WebhookSecretService` empty-result path is exercised through the delivery sink and
  a concurrent relay sibling.
- **F02:** reviewed raw connector failures are transient only at database-owned
  connection/control boundaries. Handler and sink `OSError` values are negative
  controls, so business work does not acquire a broad retry policy.
- **F03:** verification has bounded timestamp freshness, future skew, duplicate-header,
  signature-count, encoding, and length rules. The example receiver streams through a
  body limit and includes a transaction-coupled PostgreSQL inbox that detects message
  ID/body conflicts.
- **F04:** release and publication select the newest trusted workflow run and attempt
  before evaluating completion or success. Attempt-specific job evidence, pagination,
  permissions, repository/source/path/ref trust, and publisher selection share the
  same fail-closed policy. Publication downloads one attempt-specific artifact by ID,
  verifies its archive digest, and rechecks unchanged run/attempt/artifact authority
  immediately before the trusted-publisher action.
- **E01:** wheel and sdist-derived-wheel journeys and complete certification execute in
  separate clean environments using their interpreter directly. Per-artifact reports
  bind input and installed digests, package and worker-process origin, the lock digest,
  and its exact exported constraints. The locked export constrains the PEP 517 backend
  during both the initial and sdist-derived builds as well as runtime/test installation.
  Release-manifest creation and verification require the complete runtime evidence set,
  parse distribution name/version metadata, require the certification package version to
  match, and reject failed, stale, missing, or altered evidence.
- **E04:** the default migration role name and historical database-error scope are
  corrected, and the findings register now distinguishes implementation from later
  evidence stages.

## Local execution scope

The complete integration selection passed on PostgreSQL 16 and PostgreSQL 18 with
Redis 7. Exact wheel and sdist-derived environments each passed the selected database
journeys and complete real-service certification on PostgreSQL 18/Redis 7. These runs
cover T14, T21, T22, and the locally executable portion of T25 for this working tree;
they do not become `LOCAL_VERIFIED` evidence until attached to a committed source
identity under the repository's evidence policy.

## Explicitly open gates

- T05 still needs the specified two-tenant PostgreSQL revocation, expired-retiring-key,
  wrong-tenant, and terminal-finalization recovery scenario; the existing key-lifecycle
  tests and empty-result regression do not substitute for it.
- T09 still needs controlled live connector outage/restart and ambiguous-completion
  injection at each database boundary; an ordinary passing integration run is not a
  substitute.
- T19 and the hosted portions of T24–T27 need protected GitHub workflow runs for the
  exact candidate. No local fixture can authorize publication.
- T28–T31 require full-history, rights, contact-route, branch-protection, environment,
  and trusted-publisher review by repository/account owners.
- T34 requires a committed versioned alpha and its protected release evidence.
- T35–T37 remain stable/v1 external deployment, independent review, observation, and
  approval gates.

Nothing in this record claims hosted verification, external validation, release rights,
account configuration, partner usage, or publication readiness.
