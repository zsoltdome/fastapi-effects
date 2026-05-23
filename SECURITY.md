# Security policy

## Supported status

FastAPI-Mergen `0.0.x` is a pre-alpha specification and API spike. It must not be
used as a production security boundary. The first supported security claims begin
only after Milestone 2 conformance, migration, role, RLS, and crash suites pass.

## Reporting

Do not publish a suspected vulnerability before coordinated review. Report the
minimal reproduction, affected revision, impact, and any known mitigation through a
private repository security advisory when the repository is published.

Do not include real credentials, tenant data, webhook payloads, signing secrets, or
production DSNs in a report.

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
