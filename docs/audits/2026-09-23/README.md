# 0.11.0a1 public-release inventory

This inventory closes the public-artifact gap identified after the September 7 local
verification. The earlier
[`2026-09-07/published-artifact-inventory.json`](../2026-09-07/published-artifact-inventory.json)
remains an accurate, immutable record of what was observable on that date. It is not
rewritten or treated as the current release inventory.

FastAPI Effects `0.11.0a1` was released from tag `v0.11.0a1` at commit
`575f4f97769fdf6b3152822096ee1cae2668f0bf`. The exact wheel and sdist published on
PyPI match the immutable artifact selected from the successful tag evidence run. PyPI
records Trusted Publishing attestations for both distribution files, and GitHub records
one SLSA provenance statement covering both files and the bound release evidence.

The machine-readable [release inventory](release-inventory.json) records the public
URLs, hashes, workflow runs, immutable Actions artifact, and attestation identities.
PyPI's raw provenance endpoint returned `503` during the recheck, while the normal file
details page continued to show both verified attestations. This availability failure
does not change the recorded artifact identity.

Because this release contains the bundled migrations and PostgreSQL role contract,
historical-artifact upgrade testing is no longer `NOT_APPLICABLE`. Every later
candidate must create and seed a database using this exact public wheel, then upgrade
that database using the exact candidate wheel on PostgreSQL 16 and 18.
