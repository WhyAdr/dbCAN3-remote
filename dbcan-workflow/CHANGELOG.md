# Changelog

## 0.3.0

### Breaking

- Stdout is now one contract-v1 JSON envelope. The previous payload is nested under `result`; `result.legacy_status` is retained for this release and scheduled for removal in 0.4.0. Library functions keep their existing return dictionaries and legacy status values.
- Strict exit codes change: database mismatch **2 → 4**; external-stage failure **2 → 5**; deliberate guard refusals **1 → 3**. Usage stays 2 and unexpected defects stay 1. Agents must branch on `outcome.kind`. Optional `semantic-zero` returns 0 for ok/negative/refused/failed and still returns 2/1 for usage/error.
- New execution records use schema v2 with `run.state` and stage `state`. The compatibility `status` field uses v2 tokens; readers accept bound legacy records. Validation metadata retains legacy `status` for one release and adds independent structure/attestation axes.
- The sibling script entry points emit the shared envelope. Circular audit `--json` / `--tsv` are deprecated aliases for `--out-json` / `--out-tsv` and produce warnings.

### Added

- Typed outcomes, stable recovery codes, guarded envelope persistence, and a deterministic evidence-derived claim ledger.
- `describe` exposes arguments, output effects, confirmation requirements, stage assets and outcome codes. `--format markdown` adds `result.markdown` inside the envelope.
- Bounded database diff lists with full counts; `--diff-out` stores complete lists. `--sample-id` distinguishes explicit labels from FAA-stem inference without asserting identity.
- Contract regressions, generated documentation checks, integrity tooling and a minimal CI workflow.

### Integrity and compatibility

- JSON output permissions now follow `0666 & ~umask` (0644 under umask 022). The plan's default assumes the former mkstemp-derived 0600 was incidental; stricter permissions remain available through the caller's umask.
- Supplied missing/malformed/contradictory manifests remain rejected with `--allow-unattested`. Output artifact slots and explicit envelope paths cannot overwrite each other, native results or source evidence.
- Persisted envelopes use null for envelope-file self-hashes to avoid recursive hashing; stdout carries the hashes of the exact persisted envelope bytes. Those hashes are not execution attestation.
- CLI file-output guards operate on the destination file itself, avoiding false overlap refusals for sibling files while protecting every source root and selected evidence file.
- Scientific family/domain counting, native fixture files, database manifests, the package lock and the archived manifest digest are unchanged. No production database-backed search was performed for this release.
- Optional phase-4 event streams and expanded preflight check reports are deferred.
