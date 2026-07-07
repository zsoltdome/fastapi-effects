# Security policy

## Supported status

FastAPI-Mergen `0.6.0a1` is a pre-alpha assurance release. Its supported claims cover
the conformance models, runner, evidence formats, CLI, and reference fault matrix.
It does not itself make the Milestone 1 persistence API spike production ready.

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

- `mergen_migration_owner` owns objects and is never a runtime credential.
- `mergen_app` is restricted by forced RLS to one transaction-bound tenant.
- `mergen_relay` operates across tenants only on Mergen-owned control-plane tables.
- Relay connections never enter application handler code.
- Tenant GUCs propagate trusted application context; they do not authenticate the
  holder of an application database credential.
- Local publication is atomic; remote delivery is at least once.
- Raw bearer tokens, cookies, API keys, session tokens, and plaintext webhook secrets
  are never durable event or delivery fields.

The complete model and residual risks are in `docs/concepts/threat-model.md`.
