# Invoicing reference application

This is a Milestone 1 architecture fixture, not a deployable service. It proves that:

- FastAPI and OpenAPI boot without a live database;
- principal resolution and session acquisition are separate dependencies;
- the explicit UoW shape type-checks;
- typed DTOs—not ORM graph serialization—form events;
- one exact `invoice.created` route targets an explicitly keyed handler;
- entering the UoW fails before SQL until Milestone 2 implements RLS and atomic
  persistence.

Run the boot tests with:

```bash
pytest examples/invoicing/tests -q
```
