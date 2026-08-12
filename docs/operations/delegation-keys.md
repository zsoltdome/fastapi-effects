# Delegation key operations

Keep active key bytes in a secret manager or injected process secret. Configure one
active key and no more than the reviewed ring bound. Key IDs are public audit
identifiers; key material is never an ID.

## Rotate

Install a fresh random key with a new key ID and choose an overlap no longer than the
largest still-valid credential lifetime and the configured maximum overlap.
`InMemoryKeyRing.rotate()` atomically marks the former active key `retiring` and
activates the new key. New credentials immediately use the new `kid`; old
credentials verify only until both their original expiry and the overlap end.

Deploy persistent/shared key-manager implementations behind
`DelegationKeyManager` when multiple issuers run concurrently. Coordinate the new
verification key to downstream services before activating it. Never extend an old
credential expiry during rotation.

## Revoke and respond

Call `revoke(key_id)` for suspected exposure. Verification fails immediately,
including during a planned overlap. Revoking the only active key intentionally
disables new issuance until a new active key is installed through the operational
key backend.

Incident response:

1. revoke the exposed `kid` at every verifier;
2. install and distribute a new active key through the secret manager;
3. inspect token-free audit events by key ID, target ID, tenant, and trace ID;
4. rotate downstream credentials and investigate calls during the exposure window;
5. do not capture delegation tokens to enrich the investigation.

Audience changes are migrations: configure a new exact audience at issuer and
verifier, deploy it to the downstream route, and let old credentials expire. Do not
accept multiple loosely matched audience aliases.
