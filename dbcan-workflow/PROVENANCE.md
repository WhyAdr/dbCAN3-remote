# Historical provenance and glossary

## Historical statements retained verbatim

The following text is moved from the v0.2.0 README, technical provenance and environment records. Test counts and recovery claims below describe that historical work, not the current public-source verification. Referenced external case material is not included in this repository.

`dbcan-workflow/` is a self-contained skill directory with standard-library scripts, tests and fixtures, two operating profiles, a version-pinned package listing, and the recorded database manifest. JN4/JN1B case material and generated reports are outside that folder.

Use the archived run's Python 3.12.14, Linux x86_64, run_dbcan 5.2.9, and DIAMOND 2.2.8 as the recorded profile. If a new analysis is explicitly needed, create an isolated environment and install the pinned package versions:

The lock records versions, not wheel hashes. Provide the DIAMOND 2.2.8 binary from a trusted source and check its archive digest against `dbcan-workflow/environment/diamond-linux64-v2.2.8.expected.sha256`. The binary archive was not fetched or checked in this recovery.

The production database is not included. A new database-backed run needs every asset in the preserved 646-entry manifest; the archived README reports about 7.4 GB of database files. That reported size was not remeasured here. Existing-output validation, summary generation, category overlays, circular audits, and the tests need no database. Before a future database download, explain the snapshot and storage requirement, then verify a supplied cache with `scripts/dbcan_workflow.py verify-db`; the workflow has no automatic database-download step.

Thirty standalone workflow tests, seven case-wrapper regressions and fifteen legacy converter tests pass. Fresh-context agents independently reviewed a zero-hit set with rejected provenance and the two native isolate results. Source wrappers in the complete recovery bundle delegate to this canonical package; they need the sibling `repository/` tree and are not standalone files.

The fixture status file is an unbound template. Summaries infer sample names from FAA basenames; preserve isolate directories for identically named inputs. Historical outputs remain execution-unattested. No production environment, database cache or new sequence search was exercised. The detailed completion report and scientific case reports are distributed separately from this public source tree. Do not commit private isolate inputs, native outputs or evaluation case copies to the public repository.


The observed environment file records run_dbcan 5.2.9, Python 3.12.14, DIAMOND 2.2.8, and a version-pinned package listing. `environment/requirements-observed.lock` is a `pip freeze` record without package artifact hashes; it is not a hash-locked environment. The archived setup script contains the expected DIAMOND 2.2.8 Linux archive digest in `environment/diamond-linux64-v2.2.8.expected.sha256`; the archive and executable are not present here.

`environment/database_v5-2-9_5-5-2026.expected.sha256` is copied byte-for-byte from the archive's recorded final `metadata/database_sha256sums.txt` (646 entries). The archive omits the database directory, so the bytes could not be independently hashed in this recovery. The manifest supports a fail-closed comparison if a cache is supplied; it does not prove that an absent cache exists or that the historical pre-refresh files matched it.

Historical populated outputs and logs support inspection, but the JN4/JN1B archive lacks a run-wide status ledger binding input and output hashes. It remains execution-unattested. The new runner emits run ID, selected input hashes, results path, successful stage exit codes and final output hashes. These records are operational attestations, not cryptographic proof against deliberate fabrication. A changed output fails strict validation. An archive relocated to a different results path cannot automatically reuse its original path-bound ledger as a new attestation.

### Preserved environment statements

# Manifest file status

`database_v5-2-9_5-5-2026.expected.sha256` matches the archive's recorded `metadata/database_sha256sums.txt` byte-for-byte (646 entries; SHA-256 `0f20c1986c32df59723cffc20b677789ed0c12819cd0939e16788f58dea406d2`). The database directory itself is absent, so this is a preserved final observed manifest used as the comparison baseline, not a newly observed cache.

`requirements-observed.lock` matches the archived `metadata/pip-freeze.txt` byte-for-byte (SHA-256 `19b39109afc22c23f2edbb9543e0299d16ee41333cc4bcdf2860e7827170f6eb`). It pins package versions but contains no artifact hashes.

`diamond-linux64-v2.2.8.expected.sha256` records the archive digest embedded in the archived setup script. The binary archive was not present to re-hash in this recovery.

```text
Python: 3.12.14
Architecture: Linux x86_64 (archived run record)
Evidence: the preserved JN4/JN1B case bundle's metadata/software_and_run_settings.txt; this runtime record describes that archived case and is not inferred from the interpreter running the portable checks.
```

## Unresolved historical references

TODO(maintainer): identify an independently retrievable immutable identifier for “the archive” / “complete recovery bundle” referenced above. The public repository does not contain those private case files or the named sibling `repository/` tree.

TODO(maintainer): record the full case identities and externally retained source paths for JN4/JN1B if their disclosure is intended. These labels identify the historical two-isolate review in the retained text; they are not the synthetic fixture.

## Glossary

| Term | Meaning grounded in package documentation |
|---|---|
| Native results | Supplied dbCAN result files, kept unchanged during validation and reporting. |
| Diagnostics / metadata directory | A separate destination for regenerated validation, summaries and run records. |
| Overlay | A derived exact-category comparison; native membership tables remain unchanged. |
| Attested | A bound run record supplies run ID, input hashes, results path, four successful stage exit codes and final output hashes. Operational evidence, not tamper-proof proof. |
| Unattested | Results lack usable execution evidence; successful structural review alone does not establish execution. |
| Rejected | A supplied status record is malformed, incomplete, failed or mismatched and cannot be bypassed by `--allow-unattested`. |
| Claim ledger | `claims.may_say` and `claims.may_not_say` guide reporting from structured evidence, with source provenance; they are not a security boundary. |

## Historical implementation verification notes

The following records are historical, not reproducible from this repository.

- **77 standard-library tests pass**, including the original 30 unchanged tests. New coverage exercises multi-sample journals, original stage-log paths, byte/line-capped excerpts, missing/unreadable logs, stages that cannot start, skipped dependencies, independent preflight failures, strict/semantic-zero exits, false readiness flags, event-write defects and cross-artifact path collisions.

- A fresh-context skill trial inspected a missing runtime and empty cache. It reported `negative/PREFLIGHT_UNMET`, all 646 missing cache files, the independent runtime/database blockers and dependent skipped probes. It distinguished path layout from installed software, free-space observations from capacity guarantees, and readiness from search execution. Future result/metadata destinations remained absent. No install, download or sequence search occurred.

- Baseline `0b1bcc0`: all 30 original tests passed; original manifests verified. See the retained baseline raise inventory and acceptance-probe record.

- Release checks: 56 standard-library tests pass, including the original 30 unchanged tests. CLI probes cover deliberate refusals, usage, negative data, database mismatch, valid zero hits, controlled subprocess failures, and unexpected defects. Tests exercise both exit policies, path collisions, persistence, legacy/v2 status binding, claim restrictions, aliases and command discovery.

- A fresh-context skill trial used the supplied unbound fixture template, reported ATTESTATION_REJECTED, followed the sanctioned structural-only remedy, and distinguished zero-hit file observations from execution and biological absence. It used the explicit isolate label and did not modify source or fetch dependencies.

## Authorized evidence publication (2026-10-18)

The maintainer subsequently authorized publishing JN1B/JN4 and a new C14-NMZ
run separately from this portable package. The repository's `evidence/real_runs`
contains the versioned index, original-byte checksums and replay envelopes.
JN1B/JN4 remain execution-unattested historical cloud-sandbox results. C14's
new cloud execution uses the explicitly documented dbCAN 5.2.9 procfs-PID
runtime patch; it does not establish an unmodified HPC deployment. The optional
`test_evidence_bundle.py` suite replays the repository bundle, or skips when the
separately distributed data are absent. Historical statements above describe
their original scope and are retained as such.
