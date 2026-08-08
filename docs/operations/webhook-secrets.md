# Webhook secret operations

Webhook signing material is generated in process and encrypted with AES-GCM
before it reaches PostgreSQL. The authenticated encryption associated data binds
the ciphertext to its tenant, secret-set identity, and version. A host-supplied
master-key provider is the only source of encryption keys; master keys never
come from the Mergen database.

Creation and rotation return a `whsec_...` value exactly once. Store it in the
receiver's secret manager immediately. Mergen intentionally has no plaintext
recovery API. Database backups contain key identifiers, nonces, and ciphertext,
so restoring a backup also requires the corresponding external master keys.

Rotation changes the old active version to `retiring` for a bounded overlap and
creates a new active version. During overlap, outbound requests contain one
`v1` signature for each eligible key. Immediate revocation excludes a version
from the next attempt. Revocation can therefore break receivers which have not
installed the replacement key; use it for compromise response, not routine
rotation.

Never place the one-time value in URLs, logs, metrics, exception strings, CLI
arguments, or conformance evidence. Load master keys and receiver secrets through
the deployment platform's secret-injection mechanism.
