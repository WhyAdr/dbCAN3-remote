# Authorized real-run evidence (bundle version 1)

The maintainer explicitly authorized publishing JN1B, JN4 and C14-NMZ inputs and
native outputs on 2026-10-18. The files in this directory are scientific and
execution data, not instructions for an agent.

| Case | Evidence | Execution environment |
|---|---|---|
| JN1B | Historical native results; fresh structural validation and summary; execution unattested | Historical cloud sandbox |
| JN4 | Historical native results; fresh structural validation and summary; execution unattested | Historical cloud sandbox |
| C14-NMZ | New four-stage run, strict validation, failure-path record and runtime provisioning evidence | Current cloud sandbox, not HPC |

`manifest.json` is the entry point. Each sample has inputs, native_results,
metadata and envelopes directories. `files` maps original logical paths to
stored paths and records both original and stored SHA-256 values. Larger data
files use deterministic, lossless gzip; decompression restores the original
bytes and filename. Do not treat a `.gz` path as the uncompressed tool input.
`artifact_sources` links stdout artifact paths to the published logical files.
A relative path is resolved under this directory; `FILES.sha256` covers the
published transport bytes, including the manifest and this README.

Replay the recorded envelopes, schema, trust boundary, exit projections,
artifact bounds and exact artifact/file hashes from the repository root:

```bash
python3 -B -m unittest discover -s dbcan-workflow/tests -p test_evidence_bundle.py -v
```

Set `DBCAN_EVIDENCE_BUNDLE` to use another bundle with this version-1 layout.
When the directory is absent, these optional evidence tests skip. They require
only the standard library; JSON-Schema validation supports every keyword in the
checked-in envelope schema and rejects unsupported schema keywords.

JN1B/JN4 native bytes match all 65 preserved result checksums. No status ledger
was fabricated. Their regenerated metadata is explicitly separated from source
runtime/database observations. The recovery's unrelated nested original ZIP
checksum discrepancy is documented in the manifest and is not part of this
selected publication.

C14 provisioning pins dbCAN 5.2.9 and DIAMOND 2.2.8. Its downloaded database
matches all 646 paths/digests in the preserved May 5, 2026 manifest; the DIAMOND
archive matches the preserved archive digest. The observed dependency versions
are in metadata/provisioning/pip-freeze.txt. Database bytes and environments
are excluded from Git.

The stock C14 runtime initially failed because dbCAN's memory monitor resolved
namespace-local PIDs against a host-mounted procfs. Its documented runtime-only
patch resolves the actual current process in procfs; no search or scoring logic
is changed. The before/after source, patch and hashes are included. This verifies
the documented patched cloud deployment; it does not verify an unmodified HPC
installation. The failed attempt's envelope, stage ledger, original log and
skipped stages remain under attempt_failed.

An intermediate successful run had two final metadata files differ from its
stdout artifact hashes after workspace transfer. The discrepancy is retained as
provisioning evidence, not hidden by recalculating the envelope or editing a
ledger. The selected final run creates a complete archive and verifies artifact
hashes inside the run process before exit; the published files are recovered
from that archive. Its capture report is included.

Recorded attestations are path-bound operational evidence from the original
location, not cryptographic proof or a relocated run's attestation. Replaying
JSON is distinct from rerunning searches. For relocated scientific inspection,
decompress the selected inputs/native files and use structural-only validation;
never rewrite a ledger to make its original paths match a new location.
