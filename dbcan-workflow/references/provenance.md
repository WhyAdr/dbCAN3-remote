# Runtime and database provenance

The observed environment file records run_dbcan 5.2.9, Python 3.12.14, DIAMOND 2.2.8, and a version-pinned package listing. `environment/requirements-observed.lock` is a `pip freeze` record without package artifact hashes; it is not a hash-locked environment. The archived setup script contains the expected DIAMOND 2.2.8 Linux archive digest in `environment/diamond-linux64-v2.2.8.expected.sha256`; the archive and executable are not present here.

`environment/database_v5-2-9_5-5-2026.expected.sha256` is copied byte-for-byte from the archive's recorded final `metadata/database_sha256sums.txt` (646 entries). The archive omits the database directory, so the bytes could not be independently hashed in this recovery. The manifest supports a fail-closed comparison if a cache is supplied; it does not prove that an absent cache exists or that the historical pre-refresh files matched it.

The dbCAN downloader generates a root `sha256sums.txt` index that was excluded from the archived asset manifest. Verification ignores that one generated root file, then requires the observed cache to match every expected path and digest with no unlisted files.

Full database files are required only for a new search. Existing-output validation, summary generation, the exact-category overlay, circular audit, and unit tests do not read them. Do not run an automatic downloader as part of preflight.

## Validation and execution evidence

Historical populated outputs and logs support inspection, but the JN4/JN1B archive lacks a run-wide status ledger binding input and output hashes. It remains execution-unattested. The new runner emits run ID, selected input hashes, results path, successful stage exit codes and final output hashes. These records are operational attestations, not cryptographic proof against deliberate fabrication. A changed output fails strict validation. An archive relocated to a different results path cannot automatically reuse its original path-bound ledger as a new attestation.

`validate --allow-unattested` permits structural review without usable execution evidence. When supplied, a malformed, failed or mismatched status manifest still fails. `summarize` validates structure before writing tables; it does not attest execution. Keep a rejected manifest and report its rejection rather than editing it to pass.

Preflight preserves the lexical virtual-environment interpreter path (a normal venv uses a symlink), checks `sys.prefix`, probes resolved package versions, checks run_dbcan 5.2.9 and DIAMOND 2.2.8, and records executable hashes. The run_dbcan console script is invoked with the selected interpreter. Observed executable hashes are provenance, not comparisons against trusted release hashes. The compatibility shim caps `os.cpu_count()` for substrate prediction only. Resource records are before/after snapshots, not measured peak process-tree RAM.

The named May 5, 2026 database snapshot is assigned only to the exact archived manifest digest `0f20c1986c32df59723cffc20b677789ed0c12819cd0939e16788f58dea406d2`; other manifests are recorded as `custom_manifest`. Cache verification rejects unsafe manifest paths, missing files, digest differences and extra assets (apart from the generated root index). Output path guards reject overlap with source, environment, database and metadata paths. There is no automatic install, download or resume mode.

The test suite exercises orchestration with controlled subprocesses and synthetic output seeding. It is not a production database-backed search test. Such a test remains necessary before claiming a new HPC or sandbox deployment is fully verified.
