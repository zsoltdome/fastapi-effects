# FastMCP delegation integration

Install the versioned provisional integration:

```bash
pip install "fastapi-effects[fastmcp]==0.11.0a2"
```

The `0.11.0a2` integration range is FastMCP `>=3.4.7,<5`, FastAPI
`>=0.141,<0.142`, and Starlette `>=1.0.1,<2`. Hosted compatibility runs the minimum
FastMCP 3.4.7 line and the lock-resolved FastMCP 4 line against the bridge and real MCP
protocol conformance. The helper API remains provisional under ADR-017.

Use a host authentication callback to produce `TrustedCallerMetadata`; do not add
tenant, subject, parent depth, or scopes to a tool's model-visible arguments. Inside
the tool, call `FastMCPDelegationBridge.dispatch()` with the exact downstream
audience, method, path, and required scopes. The bridge strips inbound credentials,
intersects authority, signs a short-lived token, and attaches it only as
`FastAPI-Effects-Delegation`.

The downstream FastAPI application configures
`verified_delegation_dependency()` or `delegated_principal_dependency()` on every
protected route. Verification reconstructs the tenant/subject/actor/client principal
and records `delegation:<token UUID>` as opaque provenance. Required scopes and the
route authority ceiling are enforced regardless of FastMCP tool visibility.

FastMCP discovery, visibility transforms, and tool-search filters improve the client
experience; they are not authorization. A discovered tool may still receive 403,
and a hidden tool's downstream route must still require delegation.

The integration module does not import FastMCP at base-package import time. The
extra is required for the certified client/server path and examples. FastMCP's
in-memory transport is used in conformance to execute the real MCP protocol without
network variability.
