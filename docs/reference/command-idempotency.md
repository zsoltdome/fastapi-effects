# Command idempotency reference

`CommandContext` owns one outer database transaction. Pass it an idle
`AsyncSession`, authenticated `Principal`, `CommandIdentity`, and
`RequestFingerprint`. On a new command, run all protected writes with
`context.session` and call `complete()` with a bounded response. On replay, bypass
application execution and return `context.replay_response()`.

```python
prepared = await prepare_command(
    request,
    principal=principal,
    route_id="invoice.create",
)

async with session_factory() as session:
    command = command_context(session, principal=principal, prepared=prepared)
    async with command:
        if command.replayed:
            return command.replay_response()

        invoice = Invoice(tenant_id=principal.tenant_id, **await request.json())
        session.add(invoice)
        await command.emit(Event(type="invoice.created", version=1, data={"id": invoice.id}))
        response = JSONResponse({"id": invoice.id}, status_code=201)
        await command.complete(response)
        return response
```

`prepare_command()` consumes the ASGI body through a configured byte limit and
restores Starlette's request-body cache, so later `request.json()` or model parsing
sees the same bytes. JSON mode treats object-member order as insignificant. Query
order remains significant. Only configured representation/precondition headers are
fingerprinted; credential-bearing headers are forbidden.

Identity conflicts do not disclose the stored subject or fingerprint. Generation 1
is used for the first retained identity; reuse after expiry supersedes it and creates
generation 2. An unexpected durable `in_progress` row fails with a conflict instead
of allowing parallel execution.

The default replay policy allows response statuses 200–599, a 256 KiB body, 16 KiB
of allowlisted headers, and JSON/problem-JSON/plain-text media types. Streaming,
cookies, authentication/challenge headers, and hop-by-hop state are unsupported.

Command locking lasts for the application transaction. Configure PostgreSQL
`lock_timeout` and `statement_timeout` according to the endpoint's latency budget;
do not perform broker, DNS, TLS, webhook, or other remote I/O in this transaction.
