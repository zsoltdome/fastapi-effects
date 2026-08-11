# Build an idempotent FastAPI command

Authenticate the request first and construct a secret-free `Principal`. Call
`prepare_command()` before parsing the body, using a stable route name that does not
change when the URL is refactored. Then open a fresh application-role session and
enter `CommandContext`.

For a replay, return `replay_response()` immediately. For a new request, parse the
cached body, perform every business write through the context-owned session, emit
effect intent through `command.emit()`, build a non-streaming response, and pass the
same response to `complete()` before returning it.

Map `AuthenticationRequired`, `AuthorizationDenied`, `CommandConflict`, and bounded
representation errors through `command_http_exception()`. Keep application error
details in protected telemetry rather than returning stored command identity data.

Test with two simultaneous requests using one key. The required result is one
business row, one command generation, one executed response, and one response with
`Idempotency-Replayed: true`. Also test a changed body under the same key, rollback
before completion, unsafe response headers, expiry, and restoration from backup.
