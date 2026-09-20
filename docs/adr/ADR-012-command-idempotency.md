# ADR-012: Transactional command identity

Status: accepted

## Decision

Inbound command idempotency owns the outer async SQLAlchemy transaction. Its
identity is tenant UUID, stable route ID, uppercase HTTP method, and SHA-256 of the
caller's exact opaque idempotency-key bytes. The raw key is process-local input: it
is never persisted, placed in evidence, or included in default exception text.

The immutable fingerprint format is version 1. It covers path parameters, the
exact query-string bytes, normalized selected representation/precondition headers,
normalized media type, an explicit raw or canonical-JSON body mode, and the body
identity. Canonical JSON rejects duplicate semantic keys, malformed UTF-8,
non-finite numbers, and configured size violations. Subject ID is stored separately
and must match on replay; subject or fingerprint mismatch produces the same bounded
conflict.

A transaction-scoped advisory lock derives from the complete command identity and
serializes the no-row race. The first transaction writes an `in_progress` claim,
performs business writes and optional effect publication using the same session,
captures a replay-safe response, and changes the row to `completed`. A concurrent
identical transaction waits for commit and then replays. Rollback removes the claim
and every protected write. Normal exit without `complete()` is an error and rolls
back.

Expiry does not mutate completed history into a new result. The old current row is
first marked `superseded`, then a new monotonically increasing generation is
created. A database trigger freezes identity, fingerprint, creation/expiry fields,
completed response fields, and superseded rows. Retention may later remove expired
terminal history.

Replay supports bounded non-streaming `application/json`,
`application/problem+json`, and `text/plain` responses with an allowlist of safe
cache/representation headers. Authentication, cookie, challenge, hop-by-hop,
newline-bearing, unknown, and streaming state is rejected or deliberately omitted.
Replay adds `Idempotency-Replayed: true`.

The relay role has no direct command-table privileges. It receives execute access
only to a security-definer pruning function whose internal query validates the
batch bound and uses `FOR UPDATE SKIP LOCKED`. External effects performed directly
inside endpoint code are not made exactly once by this boundary; they must instead
be recorded as FastAPI Effects effect intent or use a destination-side idempotency identity.
