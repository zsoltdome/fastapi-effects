# Delegation threat model

## Trust boundaries

The host authentication layer is trusted to create `TrustedCallerMetadata`. MCP
tool arguments, client metadata, inbound headers, model-generated values, and tool
discovery state are untrusted. Never construct a `Principal`, parent depth, or scope
ceiling from tool arguments.

The issuer and verifier share an explicitly configured issuer name and key ring.
The bridge may forward only configured non-credential headers; the default allowlist
is `traceparent` and `tracestate`. Authorization, proxy authorization, cookies,
session/token/key headers, and unknown headers are dropped. The newly minted
credential is representation-hidden but remains a bearer artifact in memory and in
the single downstream request.

## Prevented confused-deputy paths

- scope intersection prevents a component from granting authority absent from the
  verified caller or route policy;
- audience binding prevents use at another downstream service;
- method/path binding prevents a credential for one operation from authorizing
  another;
- canonicalization rejects proxy/router normalization ambiguity;
- depth limits prevent indefinite re-delegation;
- short lifetime and immediate key revocation bound credential exposure;
- downstream FastAPI verification remains mandatory even if an MCP tool is hidden,
  filtered, renamed, searched, or invoked through a proxy tool.

## Residual risks

Compromise of an active symmetric signing key permits credential forgery until the
key is revoked. Protect it in an external secret manager and do not put it in source,
tokens, logs, evidence, or crash reports. A stolen delegation token can be replayed
against its exact target until expiry. Direct downstream remote effects remain
subject to their own idempotency and delivery guarantees.
