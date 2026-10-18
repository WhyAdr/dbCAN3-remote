# Contract-v1 implementation verification — v0.3.2

## Current verification

Run the gate commands below; current counts are produced by the runner rather than maintained here.

```bash
python3 -B -m unittest discover -s tests
python3 -B scripts/gen_docs.py --check
python3 -B tools/refresh_files_sha256.py --check
sha256sum -c FILES.sha256
bash -n scripts/run_dbcan_workflow.sh
```

CI also runs pyflakes on scripts. Production evidence replay is separately indexed.

## v0.3.1 — Phase 4 W4.1 / W4.2 (historical record)

- The maintainer selected `negative/PREFLIGHT_UNMET` for a completed standalone readiness report with unmet requirements. Unsafe output layout remains an immediate refusal. The strict Python facade and execution gate still refuse before starting search stages or creating result/metadata destinations.
- Run the gate commands for current test results. Phase 4 coverage exercises multi-sample journals, original stage-log paths, byte/line-capped excerpts, missing/unreadable logs, stages that cannot start, skipped dependencies, independent preflight failures, strict/semantic-zero exits, false readiness flags, event-write defects and cross-artifact path collisions.
- Historical, not reproducible from this repository: a fresh-context skill trial inspected a missing runtime and empty cache. It reported `negative/PREFLIGHT_UNMET`, all 646 missing cache files, the independent runtime/database blockers and dependent skipped probes. It distinguished path layout from installed software, free-space observations from capacity guarantees, and readiness from search execution. Future result/metadata destinations remained absent. No install, download or sequence search occurred.
- Generated documentation, shell syntax, skill validation and the refreshed complete package inventory pass. Original fixtures, original scientific regression tests, both expected reference manifests, the package lock and the archived manifest digest are unchanged from v0.3.0.
- Contract version remains 1. Readiness claims are additive and derived only from structured check states. Event journals are metadata diagnostics and do not change native-result attestation hashes. The MCP entry point is excluded.
- The optional `jsonschema` package remains unavailable; stdlib contract checks ran. CI remains configured for Python 3.10/3.12 and is inspected after publication. A new production database-backed search remains untested.

## v0.3.0 — Phases 0–3 (historical record)

The v0.3.0 implementation follows phases 0–3 of the supplied agent-interface plan. Work items are committed separately; additional guard repairs have their own bounded commits. Optional phase 4 is deferred.

- Baseline `0b1bcc0`: all 30 original tests passed; original manifests verified. See the retained baseline raise inventory and acceptance-probe record.
- Historical CLI probes cover deliberate refusals, usage, negative data, database mismatch, valid zero hits, controlled subprocess failures, and unexpected defects. Tests exercise both exit policies, path collisions, persistence, legacy/v2 status binding, claim restrictions, aliases and command discovery.
- The optional `jsonschema` package is absent in this environment. Required stdlib envelope checks ran; the optional third-party validator branch was not exercised. No dependency was installed.
- Historical, not reproducible from this repository: a fresh-context skill trial used the supplied unbound fixture template, reported ATTESTATION_REJECTED, followed the sanctioned structural-only remedy, and distinguished zero-hit file observations from execution and biological absence. It used the explicit isolate label and did not modify source or fetch dependencies.
- Generated documentation, shell syntax, complete file inventory and the skill host's basic validator pass. Scientific counting remains covered by the unchanged regression suite.
- Native fixture files, both environment checksum manifests, the version listing lock and ARCHIVED_MANIFEST_SHA256 match the baseline exactly.
- The GitHub Actions workflow is added for Python 3.10/3.12. Hosted execution cannot be exercised locally; inspect Actions after publication. No new production database-backed search was run.

## Implementation decisions

The implementation request authorizes proceeding with the supplied classification rules; the full baseline inventory was committed before typed conversion. JSON modes follow the plan's umask default. Historical statements were moved verbatim, with unresolved external references marked for the maintainer.

Envelope self-hashes are null in persisted envelopes, avoiding circular content hashes. Stdout records hashes of those exact persisted bytes. CLI file guards use resolved file destinations, protect source roots and selected evidence, and reject collisions between artifact slots. Failed runtime probes are environment refusals; actual search-stage failures are failed outcomes. Unexpected runner defects propagate to the error boundary rather than being mislabeled as stage failures.
