# Security policy

## Supported status

FastAPI Effects `0.11.0a2` is a production-hardening alpha. Core, webhook, Taskiq,
command-idempotency, and delegation claims are covered by real implementations and
conformance, but v1 promotion remains blocked on external design-partner and independent
review evidence. Supported Python/database versions are listed in `docs/compatibility.md`.

## Reporting

Do not publish a suspected vulnerability before coordinated review. Report the
minimal reproduction, affected revision, impact, and any known mitigation through a
private repository security advisory when the repository is published.

Do not include real credentials, tenant data, webhook payloads, signing secrets, or
production DSNs in a report.

## Conformance evidence security

- Adapter factories are trusted code execution and must never be tenant controlled.
- Public reports omit exception messages and retain only bounded exception types.
- Evidence fields with credential-like names are redacted; manifest metadata with
  such names is rejected.
- Known deployment secrets can be supplied indirectly through
  `--secret-canary-env`; literal command-line secret values are unsupported.
- Report destinations must be regular files, are atomically replaced, and default to
  mode `0600`.
- Certification applies only to the tested adapter, implementation version,
  capability manifest, profile, and configuration.

## Security model summary

- `fastapi_effects_migration` owns objects by default and is never a runtime credential.
- `fastapi_effects_app` is restricted by forced RLS to one transaction-bound tenant.
- `fastapi_effects_relay` operates across tenants only on FastAPI Effects-owned control-plane tables.
- Relay connections never enter application handler code.
- Tenant GUCs propagate trusted application context; they do not authenticate the
  holder of an application database credential.
- Local publication is atomic; remote delivery is at least once.
- Raw bearer tokens, cookies, API keys, session tokens, and plaintext webhook secrets
  are never durable event or delivery fields.

The complete model and residual risks are in `docs/concepts/threat-model.md`.

## Supply chain

CI runs Bandit, pip-audit, an offline high-confidence secret scan, forbidden-license
checks, and pull-request dependency review. Release builds generate a CycloneDX SBOM,
SHA-256 checksums, and GitHub/Sigstore build provenance. Actions are pinned by full commit
digest. Exceptions require an issue, owner, expiry, mitigation, and entry in the review
register; there are currently no accepted critical/high exceptions.
