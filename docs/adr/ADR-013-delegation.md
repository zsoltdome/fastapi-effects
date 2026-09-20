# ADR-013: Target-bound internal delegation

Status: accepted

## Decision

FastAPI Effects delegation is a short-lived internal credential minted from host-verified
caller metadata. It is not authentication for MCP clients and never copies an
inbound bearer token, cookie, session token, API key, or arbitrary transport
header. Host authentication supplies an immutable `Principal` and an approved
authentication-source identifier outside tool arguments.

Version 1 claims bind issuer, tenant, subject, optional actor/client, exact audience,
uppercase method, canonical target path, attenuated scopes, issued/not-before/expiry
times, opaque token ID, exact key ID, and delegation depth. HMAC-SHA-256 signs the
deterministic canonical claims bytes. The transport wrapper contains version,
payload, and signature as distinct base64url parts. Maximum configured lifetime is
one hour; the default is five minutes and bridge default is two minutes.

Target paths are ASCII absolute paths. Scheme-relative or authority-bearing forms,
empty/dot/dot-dot segments, backslashes, queries, fragments, controls, malformed
percent encodings, encoded slash/backslash/percent, and nested encoded traversal
are rejected. Unreserved percent-encodings normalize to their literal form; other
safe encodings use uppercase hex. Audience, method, and canonical path compare
exactly.

Every hop intersects requested scopes with the verified principal and component
policy. Downstream verification separately requires route scopes and rejects claim
scopes outside the route authority ceiling. A child depth is the verified parent
depth plus one and cannot exceed policy. Tool listing, visibility, or search is only
discovery behavior and never replaces downstream route verification.

Exactly one active key signs. Rotation moves it to `retiring` for a bounded overlap
and installs a new active key. A retiring key verifies only before its overlap end
and the credential's original expiry. Revocation fails verification immediately and
never extends credential lifetime. Verification selects exactly the signed `kid`;
it does not try every key.

Audit records contain approved identity IDs, audience, a hash-derived target ID,
scopes, key ID, outcome, delegation depth, token ID, and trace lineage. Tokens,
signatures, raw paths, headers, cookies, and key material are absent. A valid token
may be reused only for the same target during its short lifetime; there is no
one-time execution claim. Operations needing one-time semantics use command
idempotency at the downstream API.
