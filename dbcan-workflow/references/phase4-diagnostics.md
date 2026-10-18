# Run and readiness diagnostics

## Readiness report

Standalone `preflight` returns `result.checks[]`. Each row has a stable `id`, `state` (`pass`, `fail`, `skipped`) and structured `detail`. A failed row names its diagnostic code and message. A skipped row lists `blocked_by` check IDs; it is never a pass.

`result.ready` is true only when every required check passes. The report states readiness at assessment time, not that searches executed or will succeed. These are independent axes from structural validity and execution attestation.

| Outcome | Meaning | Strict exit |
|---|---|---:|
| `ok/OK` | Every required readiness check passed. | 0 |
| `negative/PREFLIGHT_UNMET` | The diagnostic report completed; failed or skipped requirements remain. | 4 |
| `refused/PATHS_OVERLAP` | Unsafe output layout; no diagnostic probes are started. | 3 |

`semantic-zero` projects the first three outcomes to exit 0 without changing their meaning. Preflight writes no default files; use a separate, guarded `--envelope-out` to preserve the report. No dependency or database is installed or downloaded.

Independent checks continue after ordinary unmet requirements. Dependency-bound probes are skipped: for example, a missing Python executable blocks its smoke test and identity check, while an available DIAMOND executable and the supplied database can still be inspected. A runtime coding defect remains `error/INTERNAL_ERROR`, rather than an unmet requirement.

| Check IDs | Requirement or observation |
|---|---|
| `output_paths`, `destinations_fresh` | Disjoint protected paths and fresh run destinations. Unsafe overlap is refused before probes. |
| `thread_budget`, `resource_profile` | Positive integer CPU budget and supported profile. |
| `input_pair` | Structurally valid, matching FAA/GFF3 pair. |
| `resource_allocation`, `cpu_budget` | Detect allocation and enforce the requested limit; unknown allocation blocks readiness. |
| `python_executable`, `run_dbcan_executable`, `diamond_executable` | Selected files exist and are executable. |
| `environment_layout` | All selected executables belong to the same environment bin directory. |
| `python_probe`, `python_identity` | Selected interpreter responds; its prefix and dbCAN version match. Venv interpreter symlinks retain their lexical invocation path. |
| `run_dbcan_version`, `diamond_version` | Probe dbCAN 5.2.9 and DIAMOND 2.2.8. |
| `executable_hashes` | Record executable hashes as provenance, without treating them as trusted release signatures. |
| `storage_snapshot` | Record free disk bytes; this observation does not impose a new capacity threshold or predict output size. |
| `database_assets`, `database_manifest` | Require stage assets and the entire preserved manifest, including rejection of unexpected files. A mismatched cache is hashed once per report; displayed difference lists are limited to 20 entries per category with full counts. |

The Python `run_preflight` facade remains strict and stops at its first blocker with the original typed exception. `collect_preflight` exposes the complete safe diagnostic report. `run` invokes strict preflight and checks any structured report again before creating destinations: a true readiness flag cannot override failed or skipped checks. A refusal from `run` can include a partial `result.checks` report; use standalone preflight for all independent diagnostics. No search stage starts unless every required check passes.

## Event journals and failure context

Each started sample owns `metadata/<sample>/events.jsonl`. The runner appends and fsyncs one JSON object per event, using one writer per fresh sample directory. Existing journals are never resumed or truncated. Fields are `ts`, `run_id`, `sample`, `stage` (null for a sample-wide event), `event`, and optional structured `details`.

Events include `run_started`, `stage_started`, `stage_succeeded`, `stage_failed`, `stage_skipped`, `validation_started`, `validation_succeeded`, `run_succeeded`, and `run_failed`. A failed sample does not prevent subsequent samples from being attempted. Pending stages are recorded as skipped; an unavailable stage executable still gets a failed event. Unexpected bookkeeping defects remain tool errors, with no retained success completion marker.

Stage logs stay in `results/<sample>/logs/`. Envelopes index them with artifact role `stage_log`, including unavailable logs with `written: false`; journals have role `event_log`. A `STAGE_FAILED` result includes `sample`, `stage`, `exit_code` (null if the subprocess could not start), `log_path`, `log_tail`, and `log_tail_truncated`. Missing/unreadable logs add `log_tail_error` without replacing the original stage failure.

`log_tail` retains at most 40 lines and 8192 UTF-8 bytes. Reading is bounded to 8193 source bytes, even for huge logs or individual lines. A truncated excerpt can begin mid-line; inspect the full log when needed. JSON escaping can expand transport size beyond the plain-text field limit.

Journals are diagnostics, not execution-attestation substitutes. They live outside native results, so appending a diagnostic record does not change the native hash inventory. Path guards prevent an explicit envelope from replacing journals, status ledgers or scientific summaries. Native fixtures and scientific counting rules remain unchanged.
