# Runtime and database provenance

Read [historical provenance and glossary](../PROVENANCE.md) for the retained case narrative and external-source limitations. The recorded runtime is Python 3.12.14 on Linux x86_64, dbCAN 5.2.9 and DIAMOND 2.2.8. The package listing pins versions without artifact hashes. Database bytes and the DIAMOND binary archive are not bundled; a checksum listing alone does not establish that absent bytes were verified.

The dbCAN downloader generates a root `sha256sums.txt` index that was excluded from the archived asset manifest. Verification ignores that one generated root file, then requires the observed cache to match every expected path and digest with no unlisted files.

Full database files are required only for a new search. Existing-output validation, summary generation, the exact-category overlay, circular audit, and unit tests do not read them. Do not run an automatic downloader as part of preflight.

## Validation and execution evidence

`validate --allow-unattested` permits structural review without usable execution evidence. When supplied, a malformed, failed or mismatched status manifest still fails. `summarize` validates structure before writing tables; it does not attest execution. Keep a rejected manifest and report its rejection rather than editing it to pass.

Preflight preserves the lexical virtual-environment interpreter path (a normal venv uses a symlink), checks `sys.prefix`, probes resolved package versions, checks run_dbcan 5.2.9 and DIAMOND 2.2.8, and records executable hashes. The run_dbcan console script is invoked with the selected interpreter. Observed executable hashes are provenance, not comparisons against trusted release hashes. The compatibility shim caps `os.cpu_count()` for substrate prediction only. Resource records are before/after snapshots, not measured peak process-tree RAM.

The named May 5, 2026 database snapshot is assigned only to the exact archived manifest digest `0f20c1986c32df59723cffc20b677789ed0c12819cd0939e16788f58dea406d2`; other manifests are recorded as `custom_manifest`. Cache verification rejects unsafe manifest paths, missing files, digest differences and extra assets (apart from the generated root index). Output path guards reject overlap with source, environment, database and metadata paths. There is no automatic install, download or resume mode.

The test suite exercises orchestration with controlled subprocesses and synthetic output seeding. It is not a production database-backed search test. Such a test remains necessary before claiming a new HPC or sandbox deployment is fully verified.

## Status vocabulary v2

Stage-status, workflow-summary and completion records carry `schema_version: 2` and `run.state` (`pending`, `running`, `stages_succeeded`, `succeeded`, `failed`, `incomplete`). Stage records carry `state` (`pending`, `running`, `succeeded`, `failed`, `skipped`); the compatibility `status` field uses the same v2 token. Readers accept legacy `complete`, `stages_complete`, and stage `completed` tokens without weakening hash, path or exit-code binding. Contradictory aliases are rejected.

Validation metadata retains its legacy `status` for one release and adds independent `evidence.structure` and `evidence.attestation` fields. A supplied missing or malformed status file is rejected even in structural-review mode.

Recorded in v0.2.0 source; never fetched by this tool; not re-verified: `https://dbcan.s3.us-west-2.amazonaws.com/db_v5-2-9_5-5-2026`. The unused `SNAPSHOT_BASE_URL` constant was removed; no downloader was introduced.

## Readiness and event diagnostics

See [Phase 4 diagnostics](phase4-diagnostics.md) for the readiness check report, strict execution gate, event journals and capped log excerpts. Readiness and event observations do not replace a bound stage-status manifest or imply that a search executed.

Every claim carries a literal source anchor, checked against the package text.
CL-A1 and CL-N10 cite PROVENANCE.md for operational attestation limits. CL-D1
keeps static text and carries only validated nonnegative integer file count and
lowercase 64-hex manifest digest in `facts`; malformed facts suppress that claim.
See [claim scope matrix](../docs/claim-scopes.md) for command applicability.
