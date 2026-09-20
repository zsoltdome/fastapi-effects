# Operating conformance certification

## 1. Create a trusted adapter factory

Expose a zero-argument synchronous or asynchronous factory:

```python
# myapp/fastapi_effects_conformance.py
async def create_driver() -> MyBoundaryDriver:
    return MyBoundaryDriver(test_database_url=settings.conformance_database_url)
```

The factory is application code and is imported with full process authority. Never
accept the `module:factory` string from an HTTP request, tenant setting, webhook, or
other untrusted source.

## 2. Inspect the manifest

```bash
fastapi-effects conformance manifest \
  --adapter myapp.fastapi_effects_conformance:create_driver \
  > build/conformance/manifest.json
```

Validate a saved manifest without importing the adapter:

```bash
fastapi-effects conformance manifest \
  --input build/conformance/manifest.json
```

Exactly one of `--input`, `--adapter`, or `--reference` is permitted.

## 3. Run a profile

```bash
fastapi-effects conformance run \
  --adapter myapp.fastapi_effects_conformance:create_driver \
  --profile core \
  --format json \
  --output build/conformance/report.json
```

Profiles: `core`, `delivery`, `security`, `complete`.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | selected profile certified |
| 1 | valid run completed but profile was not certified |
| 2 | configuration, loading, parsing, or output error |

Use `--fail-fast` only for interactive diagnosis. CI evidence should normally contain
every selected check. `--timeout` overrides each scenario's default timeout and is
bounded to 300 seconds.

## 4. Produce CI-native formats

```bash
# JUnit
fastapi-effects conformance run --reference --profile complete \
  --format junit --output build/conformance/junit.xml

# SARIF
fastapi-effects conformance run --reference --profile complete \
  --format sarif --output build/conformance/results.sarif

# Human review
fastapi-effects conformance run --reference --profile complete \
  --format markdown --output build/conformance/report.md
```

JSON is the archival source of truth. JUnit, SARIF, and Markdown are projections.

## 5. Verify archived evidence

```bash
fastapi-effects conformance verify \
  --manifest build/conformance/manifest.json \
  --report build/conformance/report.json
```

Verification checks:

- strict UTF-8 JSON and duplicate-key rejection;
- supported schema and contract versions;
- report digest;
- manifest digest binding;
- derived status, counts, and certification;
- complete invariant coverage for the selected profile.

Verification does not execute the adapter again.

## 6. Evidence permissions and retention

The CLI creates report files with mode `0600` and atomically replaces an existing
regular file. It refuses symbolic-link destinations and non-regular targets. The
operator remains responsible for directory permissions, artifact-store access,
retention, and deletion.

Recommended defaults:

- pull-request artifacts: 14 days;
- release-candidate evidence: retain with the release;
- production deployment evidence: follow the organization's audit-retention policy;
- never upload secret-canary source files or environment dumps.

## 7. Reference and fault validation

The built-in reference driver can validate the suite itself:

```bash
fastapi-effects conformance run --reference --profile complete
fastapi-effects conformance run --reference --profile complete \
  --fault stale_lease_accepted
```

The first command must certify. The second must return exit code 1. The Milestone 7
audit executes the complete fault matrix automatically.

## 8. Release gate

```bash
python scripts/audit_milestone_seven.py \
  --json-output build/conformance/audit.json \
  --markdown-output build/conformance/audit.md
```

The audit checks source structure, metadata, packaged specifications, every reference
profile, every injected fault, all report formats, public API boundaries, pinned
GitHub Actions, Git authorship, branch ancestry, commit-message length, clean state,
and Git object integrity. Commit `6b8d362` is an explicit immutable recovery-baseline
exception for its original email and `.gitignore` subject; later commits remain subject
to the normal identity and subject rules. The exception preserves provenance rather
than rewriting published history. Governance evaluates commits reachable from
controlled local branches; fetched remote bot or contributor refs are outside that
authorship assertion and do not weaken checks on `main`.

## 9. Release evidence authority and artifact isolation

The tag workflow discovers required workflows first, validates repository/source
repository, source SHA, workflow path, `push` event, and source branch, then selects the
highest trusted workflow run number and rerun attempt. Only that attempt's jobs may
satisfy the required matrix. A newer failed, queued, running, cancelled, or incomplete
attempt cannot fall back to an older green run. GitHub API errors, malformed pages, or
missing attempt metadata are unavailable evidence and fail the gate.

Wheel and sdist verification use separate clean virtual environments, invoke each
environment's interpreter directly from a neutral directory, strip `PYTHONPATH` and
`PYTHONHOME`, and assert package origin under that environment. The sdist is first built
to a derived wheel whose digest is recorded. The initial PEP 517 build, the sdist-derived
build, and runtime/test dependency installation are constrained by an exact export of the
checked lock, including the locked build backend. Both the constraints digest and lock
digest are carried into each per-artifact certification manifest. Each environment runs
the selected database journeys and complete real-service certification, including
same-process and Taskiq worker-process origin checks.

Release-manifest schema v2 requires the constraints export, runtime result, and both
artifact-specific certification manifests and reports. It parses wheel `METADATA` and
the sdist's root `PKG-INFO`, requiring their project/version to match the promotion
target before binding their bytes. Each certification manifest's package version must
match the same target. The evidence files are semantically validated, then
hashed with the SBOM and checksums together with source SHA, lock digest, workflow run ID,
and workflow attempt.

Publication selects that authoritative attempt first, resolves exactly one
attempt-specific Actions artifact, downloads it by immutable artifact ID, verifies the
artifact archive digest, and verifies the enclosed release manifest; it never rebuilds.
Immediately before the trusted-publisher action it repeats workflow and artifact
selection and requires the run ID, attempt, artifact ID, and digest to remain unchanged.
GitHub selection and PyPI upload cannot be one atomic transaction, so repository and
environment authorization remain required around the small post-recheck boundary.
