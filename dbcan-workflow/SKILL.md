---
name: dbcan-workflow
description: Prepare, run, validate, and report dbCAN 5.2.9 CAZyme analyses from bacterial protein FASTA and Bakta GFF3 inputs, or audit existing dbCAN output directories. Use for explicit-path workflow repair, result validation, multi-family/domain evidence summaries, CGC category overlays, circular-contig checks, and database/runtime preflight.
---

# dbCAN workflow

## Choose the task

**Use when:** preparing paired FAA/GFF3 inputs, inspecting existing dbCAN outputs, reporting evidence, auditing CGCs or planning a confirmed new search.
**Do NOT use when:** running searches merely to regenerate reports, downloading databases, or treating a derived overlay as an upstream patch.

Run these tools locally on the agent host; “remote” describes the human's access. Inventory supplied paths first. Keep inputs, native results, diagnostics, environment and database destinations separate. Preserve native files.

Use `python3 -B scripts/dbcan_workflow.py describe` for arguments, expected outputs, database assets and possible outcomes. Use this CLI as the agent entry point; `run_dbcan_threadcap.py` is an internal, version-guarded shim for substrate prediction, not an agent entry point.

## Read the envelope

1. Parse stdout as one JSON document. Branch on `outcome.kind`, not on the exit code.
2. `refused` is a correct, deliberate result, not a failure to work around. Follow only `refusal.remediation`; never attempt anything in `refusal.forbidden`. Surface the refusal and its code to the user.
3. `negative` means the tool worked and the answer is no. Report it; do not retry.
4. `failed` means a stage failed; read the artifact with role `stage_log`; rerun only into fresh directories.
5. `error` is a tool defect; report it with the stderr traceback.
6. In any report, assert only what is in `claims.may_say`, and never what is in `claims.may_not_say`. The ledger is guidance with provenance, not a security boundary.

Read the command payload under `result`. `legacy_status` is transitional; use `outcome` and `evidence` for decisions. Strict process exits are 0/1/2/3/4/5 for ok/error/usage/refused/negative/failed. If a shell discards nonzero stdout, use `--exit-policy semantic-zero`; semantic outcomes remain binding. `--help` prints help instead of an envelope. `describe --format markdown` places its rendering in `result.markdown` within the envelope.

## Review existing results

Use the exact selected native directory and separate diagnostics:

```bash
python3 -B scripts/dbcan_workflow.py validate \
  --faa /inputs/sample.faa --gff /inputs/sample.gff3 \
  --results-dir /native/sample --metadata-dir /diagnostics/sample \
  --status-file /metadata/sample/stage_status.json --sample-id isolate_a
python3 -B scripts/dbcan_workflow.py summarize \
  --faa /inputs/sample.faa --gff /inputs/sample.gff3 \
  --results-dir /native/sample --metadata-dir /diagnostics/sample/summary \
  --sample-id isolate_a
```

A bound attestation requires a run ID, both input hashes, the selected results path, four successful stage exit codes and the final output inventory. File presence or declared success is insufficient. A supplied failed, missing, malformed or mismatched manifest is rejected even with `--allow-unattested`.

For structural review without usable attestation, omit `--status-file` and add `--allow-unattested`. Preserve and explicitly report any earlier rejection. Describe valid results as structurally valid, execution-unattested; never manufacture a status record. The fixture's `stage_status.template.json` is an unbound template, not execution evidence.

Pass `--sample-id` for identically named FASTAs. `sample_source: faa_stem` and `SAMPLE_INFERRED` expose inferred labels; neither an explicit label nor a filename verifies isolate identity.

## Prepare or run a new analysis

Prepare an adapter with `prepare --faa … --gff … --out-gff … --report …`. Inspect `describe` for circular audit and overlay paths. The overlay's `--dbcan-version 5.2.9` is a caller-supplied compatibility guard, not independent runtime evidence; corroborate historical version metadata.

Obtain user confirmation for a **new search**. Before provisioning or downloading, explain the pinned runtime, database snapshot and reported storage requirement from `references/provenance.md`. Validation, summaries, overlays, audits and fixture tests need only the standard library.

Standalone `preflight` completes safe independent checks and reports unmet requirements as `negative/PREFLIGHT_UNMET` with `result.checks`. Treat `skipped` as blocked, never passed; only `result.ready: true` with every check passed permits execution. Unsafe paths are refused before probes. The strict Python `run_preflight` API and `run` still stop at the first blocker; their refusal can include a partial report.

For a failed run, inspect the per-sample `events.jsonl` in metadata and the `stage_log` artifacts at their original results paths. Failure context includes a log excerpt capped at 40 lines / 8 KiB; use the full log if truncated. Journals are append-only diagnostics, not attestation or a resume mechanism. Read `references/phase4-diagnostics.md` for check dependencies, event fields and failure semantics.

For a confirmed search, supply the exact preserved database cache, run `verify-db` and `preflight`, then run:

```bash
python3 -B scripts/dbcan_workflow.py run \
  --input-dir /inputs --results-dir /fresh/results --metadata-dir /fresh/metadata \
  --db-dir /verified/cache --expected-manifest /reference/expected.sha256 \
  --env-dir /runtime/dbcan-5.2.9 --samples isolate_a isolate_b \
  --threads 2 --profile sandbox
```

Use `profiles/sandbox.yaml` or `profiles/hpc.yaml` to select an explicit thread budget within the detected allocation. The runner refuses duplicate/unsafe sample names, used destinations, unverified assets, incompatible environments and excessive CPU requests before creating results. There is no automatic download, install or resume.

## Interpret the evidence

- Keep positive method count, same-family agreement across methods, unique proteins per family, query-aligned HMM/domain instances, and DIAMOND reference-family associations as separate measures.
- Allow one protein to contribute to multiple family and class totals; label these totals as overlapping.
- Treat a DIAMOND family listed on a reference protein as a homology association, not proof that the query has that domain.
- Keep GH0/GT0 and other zero-root labels visible as unresolved evidence, outside resolved-family counts.
- Describe dbCAN substrate and PUL matches as computational predictions. Compare them with protein annotations and neighborhood members before writing substrate-specific claims.
- Record circular topology from the original GFF3. Audit terminal signature windows; do not join across an origin unless the configured signature and null-gene rules support it.
- Create a version-guarded exact-category overlay in a separate directory. Never overwrite native CGC tables or describe the overlay as an upstream package patch.

Read `references/reporting.md` for scientific counting rules, `references/provenance.md` for runtime and database evidence, and `PROVENANCE.md` for historical context and glossary. Before changing code, run `python3 -B -m unittest discover -s tests -v`.

## Expected command outputs

<!-- BEGIN GENERATED:commands -->
| Command | Purpose | Writes |
|---|---|---|
| `prepare` | Validate paired inputs and prepare standalone CDS GFF. | --out-gff, --report, --envelope-out (optional) |
| `validate` | Validate the exact native results and optional execution attestation. | output_validation.json, results_observed.sha256 (or --observed-manifest), envelope.validate.json, --envelope-out (optional) |
| `summarize` | Write overlap-aware scientific evidence tables. | summary.json, protein_family_associations.tsv, domain_instances.tsv, method_agreement.tsv, family_protein_counts.tsv, class_family_comparison.tsv, candidate_evidence.tsv, envelope.summarize.json, --envelope-out (optional) |
| `verify-db` | Compare a supplied cache with every expected path and digest. | --observed-manifest, --diff-out (optional), --envelope-out (optional) |
| `preflight` | Report every safe readiness check; unmet requirements are a negative result. | --envelope-out (optional) |
| `run` | Run four stages only after confirmed preflight into fresh roots. | native results, logs/*, inputs/*, stage_status.json, output_validation.json, results_observed.sha256, scientific_summary/*, completion.json, workflow_summary.json, events.jsonl (per sample), envelope.run.json, --envelope-out (optional) |
| `audit-circular` | Audit circular terminal windows against original topology. | --out-json, --out-tsv, --envelope-out (optional) |
| `cgc-overlay` | Write a derived exact-category comparison without modifying native tables. | --corrected-members, --corrected-summary, --changes, --report, --envelope-out (optional) |
| `describe` | Describe arguments, effects and the contract without executing work. | --envelope-out (optional) |

Required database assets for a new search:
- `CAZyme_annotation`: `CAZy.dmnd`, `dbCAN.hmm`, `dbCAN-sub.hmm`, `fam-substrate-mapping.tsv`.
- `gff_process`: `TCDB.dmnd`, `TF.hmm`, `TF.dmnd`, `STP.hmm`, `peptidase_db.dmnd`, `sulfatlas_db.dmnd`.
- `cgc_finder`: none.
- `substrate_prediction`: `PUL.dmnd`, `dbCAN-PUL.xlsx`, `dbCAN-PUL`.
<!-- END GENERATED:commands -->

## Recovery by outcome code

<!-- BEGIN GENERATED:recovery -->
| Code | Kind | Sanctioned remediation | Forbidden workarounds |
|---|---|---|---|
| `OK` | ok | The requested operation completed. | — |
| `USAGE_INVALID` | usage | The command line is invalid. | — |
| `PATHS_OVERLAP` | refused | Choose fresh, disjoint output roots. | Do not reuse inputs, native results, environment or database directories as outputs. |
| `ATTESTATION_REQUIRED` | refused | Pass the run's stage_status.json. Use structural review only; do not claim execution. | Do not create or edit a manifest to satisfy this check. |
| `ATTESTATION_REJECTED` | refused | Report and preserve the rejection. Supply a different bound manifest. Omit the rejected manifest and request structural review; retain the rejection in the report. | Do not edit the rejected manifest to make it pass. |
| `RESULTS_DIR_MISSING` | refused | Supply the exact existing native results directory. | Do not create an empty directory to satisfy this check. |
| `INPUT_MISSING` | refused | Supply the existing input paths. | — |
| `INPUT_MISMATCH` | refused | Supply the matching FAA/GFF3 pair. | — |
| `SAMPLE_ID_UNSAFE` | refused | Use distinct plain isolate names without path traversal. | — |
| `ENV_UNMET` | refused | Provision the selected pinned environment and DIAMOND 2.2.8. | Do not install or download without user confirmation. |
| `DB_UNVERIFIED` | refused | Run verify-db on a supplied cache and preserved manifest. | Do not download databases without explicit user confirmation. |
| `THREADS_EXCEED_ALLOCATION` | refused | Lower the thread budget to the detected allocation. | — |
| `MANIFEST_PATH_UNSAFE` | refused | Use the preserved checksum manifest. | — |
| `VERSION_UNSUPPORTED` | refused | Use the overlay only for corroborated dbCAN 5.2.9 results. | — |
| `STRUCTURE_INVALID` | negative | The supplied data are structurally inconsistent. | — |
| `DB_MISMATCH` | negative | The cache does not match the expected manifest. | — |
| `PREFLIGHT_UNMET` | negative | Preflight report completed; satisfy every failed or skipped requirement before running. | — |
| `STAGE_FAILED` | failed | An external stage failed; inspect its log and rerun into fresh directories. | — |
| `INTERNAL_ERROR` | error | An unexpected tool defect occurred; report the stderr traceback. | — |
<!-- END GENERATED:recovery -->
