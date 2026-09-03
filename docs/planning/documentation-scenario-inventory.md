# Documentation scenario inventory

The machine-readable [inventory](documentation-scenario-inventory.json) accounts for
every Python, Bash, shell, and console fenced block in the README, documentation tree,
and example READMEs. Each block is content-hashed and classified as executed,
syntax-checked, manual/operator-only, or historical. `scripts/check_documentation.py`
fails when a block is added or changed without reviewing that classification and its
evidence.

The maintained end-to-end journey set is installation, quickstart, relay, webhook
lifecycle, replay, Taskiq, and FastMCP. All seven have local evidence. Clean
wheel/sdist installation and optional imports cross an artifact boundary; the
database-backed journeys currently run from the working tree. They must therefore be
rerun from an exact committed candidate artifact before R2.4 or release promotion can
be complete.

Manual/operator commands remain explicit rather than being counted as executed. These
include backup/restore, commands using deployment DSNs, custom application adapters,
and the webhook receiver process. Historical planning snippets are preserved but are
not current user instructions.
