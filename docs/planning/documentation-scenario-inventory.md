# Documentation scenario inventory

The machine-readable [inventory](documentation-scenario-inventory.json) accounts for
every Python, Bash, shell, and console fenced block in the README, documentation tree,
and example READMEs. Each block is content-hashed and classified as executed,
syntax-checked, manual/operator-only, or historical. `scripts/check_documentation.py`
fails when a block is added or changed without reviewing that classification and its
evidence.

The maintained end-to-end journey set is installation, quickstart, relay, webhook
lifecycle, replay, Taskiq, and FastMCP. All seven have local evidence and a clean
wheel/sdist-derived-wheel harness. The protected tag workflow reruns the selected
database, relay, replay, key-lifecycle, Taskiq-worker, and conformance journeys from
each exact candidate environment and binds the reports into the release manifest.
Local execution has no release authority; only the protected report does.

Manual/operator commands remain explicit rather than being counted as executed. These
include backup/restore, commands using deployment DSNs, custom application adapters,
and the webhook receiver process. Historical planning snippets are preserved but are
not current user instructions.

The automated journey verifies commands, package origin, transaction behavior, and
recovery semantics. It is not a substitute for FE-008's unfamiliar-developer usability
record; time-to-first-effect and author intervention remain unclaimed until a real
participant records them.
