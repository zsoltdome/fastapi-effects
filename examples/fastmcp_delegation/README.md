# FastMCP delegation example

`build_apps()` receives a key from the deployment secret boundary, a host-owned
trusted-caller provider, and an HTTP client for the downstream service. The tool
accepts only the business argument; tenant, subject, scopes, and delegation depth
never become model-controlled inputs. The downstream FastAPI dependency remains the
final authorization boundary.
