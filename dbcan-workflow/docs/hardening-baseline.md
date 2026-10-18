# Hardening baseline (5ec0414)

Measured locally before changing implementation:

| Check | Observation |
|---|---|
| Standard-library tests | 77 pass |
| Generated documentation and inventory | In sync; all 58 inventory entries verify |
| R1 duplicate hostile FASTA ID | Reaches outcome.summary and findings message |
| R3 explicit ../evil sample label | Accepted; expected refusal probe fails |
| R4 missing, misspelled, unknown command | Misreported as describe |
| R4 nonfinite dispatch result | Final serialization raises ValueError without JSON stdout |

All four regression probes fail with expected-failure decorators removed; each fails at the intended assertion (NaN at serialization). No production database-backed execution is represented by this baseline.
