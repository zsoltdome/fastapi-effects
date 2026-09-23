# Release and candidate inventories

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

The machine-readable [0.11.0a1 release inventory](release-inventory.json) records the public
URLs, hashes, workflow runs, immutable Actions artifact, and attestation identities.
PyPI's raw provenance endpoint returned `503` during the recheck, while the normal file
details page continued to show both verified attestations. This availability failure
does not change the recorded artifact identity.

On September 23 the original Actions ZIP, both distributions, the manifest, checksums,
certification reports, lock constraints, SBOM, and conformance schemas were attached to
the GitHub release without rebuilding them. A fresh unauthenticated download of the ZIP
matched SHA-256
`f0e913257347e61416ab04bec97e7126d08168e051b5ee3089db54849c7b9c7c`;
extracting it and verifying the original manifest with the tag's lock file passed. The
inventory records every manifest-bound asset hash and the durable download route.

The bounded [repository-controls snapshot](repository-controls.json) records the
authenticated owner readback of branch, tag, environment, Actions, reporting, and last
observed publisher controls. It also records the single-owner limitations instead of
mistaking an approval pause for independent review.

Because this release contains the bundled migrations and PostgreSQL role contract,
historical-artifact upgrade testing is no longer `NOT_APPLICABLE`. Every later
candidate must create and seed a database using this exact public wheel, then upgrade
that database using the exact candidate wheel on PostgreSQL 16 and 18.

The separate [0.11.0a2 inventory](release-inventory-v0.11.0a2.json) records the exact
tagged candidate without rewriting either historical record. Protected release-evidence
run `35876379003.2` passed, including the public-`0.11.0a1` upgrade journey on
PostgreSQL 16 and 18, and GitHub records SLSA provenance for the candidate files. The
inventory deliberately records GitHub release publication, durable release assets,
PyPI publication, and both PyPI file attestations as pending until FE-008 is completed
by an unfamiliar developer and the protected publish workflow succeeds.
