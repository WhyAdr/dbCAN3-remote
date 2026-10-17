# Contract-v1 implementation verification

The v0.3.0 implementation follows phases 0–3 of the supplied agent-interface plan. Work items are committed separately; additional guard repairs have their own bounded commits. Optional phase 4 is deferred.

- Baseline `0b1bcc0`: all 30 original tests passed; original manifests verified. See the retained baseline raise inventory and acceptance-probe record.
- Release checks: 56 standard-library tests pass, including the original 30 unchanged tests. CLI probes cover deliberate refusals, usage, negative data, database mismatch, valid zero hits, controlled subprocess failures, and unexpected defects. Tests exercise both exit policies, path collisions, persistence, legacy/v2 status binding, claim restrictions, aliases and command discovery.
- The optional `jsonschema` package is absent in this environment. Required stdlib envelope checks ran; the optional third-party validator branch was not exercised. No dependency was installed.
- A fresh-context skill trial used the supplied unbound fixture template, reported ATTESTATION_REJECTED, followed the sanctioned structural-only remedy, and distinguished zero-hit file observations from execution and biological absence. It used the explicit isolate label and did not modify source or fetch dependencies.
- Generated documentation, shell syntax, complete file inventory and the skill host's basic validator pass. Scientific counting remains covered by the unchanged regression suite.
- Native fixture files, both environment checksum manifests, the version listing lock and ARCHIVED_MANIFEST_SHA256 match the baseline exactly.
- The GitHub Actions workflow is added for Python 3.10/3.12. Hosted execution cannot be exercised locally; inspect Actions after publication. No new production database-backed search was run.

## Implementation decisions

The implementation request authorizes proceeding with the supplied classification rules; the full baseline inventory was committed before typed conversion. JSON modes follow the plan's umask default. Historical statements were moved verbatim, with unresolved external references marked for the maintainer.

Envelope self-hashes are null in persisted envelopes, avoiding circular content hashes. Stdout records hashes of those exact persisted bytes. CLI file guards use resolved file destinations, protect source roots and selected evidence, and reject collisions between artifact slots. Failed runtime probes are environment refusals; actual search-stage failures are failed outcomes. Unexpected runner defects propagate to the error boundary rather than being mislabeled as stage failures.
