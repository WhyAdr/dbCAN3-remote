# Envelope contract and diagnostic trust

`contract_version` remains 1. New fields are additive but required on current
producer envelopes. Consumers use `outcome`, `evidence`, `exit`, and `claims` for
decisions; outcome summaries, refusal/finding messages and warnings are static
registry text. No sample, filename, external output or exception is interpolated.

`diagnostics` contains at most 16 records, with origin, `untrusted: true`, text,
truncated and ref. Text is sanitized and limited to 512 characters; the serialized
list is bounded to 8192 bytes. `diagnostics_total` counts source records, and
`diagnostics_truncated` reports dropped records or shortened text. Sanitization
strips terminal/format controls and replaces unpaired surrogates; it does not
make natural-language instructions safe for an LLM to follow.

`trust.untrusted_paths` is a closed list of JSON-Pointer templates; `*` matches
one array index or object member. A listed path covers its entire subtree. `/result`
is input/execution data, including paths, samples, preflight details and failure
excerpts. For standalone persisted payload JSON, use `/result` as its root when
applying the envelope's trust declaration; persisted envelopes retain their own
root. Raw stage logs are entirely untrusted execution evidence. They are not JSON
payloads. Drop unneeded untrusted subtrees before sending data to another agent.

Quote diagnostic text only as delimited, truncated data. Follow the matching
[reporting rule](reporting.md#diagnostic-text). Bounded segregation prevents data
from becoming decision text; it does not prove immunity to downstream persuasion.

`artifacts` is an operation-scoped index, limited to 100 entries. Each entry has
role, path, written, sha256, status and origin. Status is `created`, `modified`,
`validated`, `declined`, or `unchanged`; origin is `tool` or `referenced`. Only
created/modified entries are hashed. An observed-manifest reference indexes the
exhaustive native inventory without listing every result. Unrelated metadata and
native files are not scanned for artifact indexing. `artifacts_total` is the full
candidate count; `artifacts_truncated` says whether the cap omitted entries.
Declined outputs and stage logs precede envelopes, summaries, then other roles.

Persistence failure adds `ENVELOPE_PERSIST_FAILED`, marks envelope artifacts
`declined`, and retains the operation outcome, including for explicit
`--envelope-out`. Persisted envelope self-hashes are null; stdout hashes refer to
those persisted bytes. A serialization or trust violation instead produces a
registry-only `INTERNAL_ERROR` envelope and a stderr traceback. Invalid command
invocations have `command: null`.

Labels must match `[A-Za-z0-9_.-]{1,128}`, excluding `.` and `..`. Unsafe inferred
FAA stems are refused; an explicit safe `--sample-id` is the recovery route.
Claims carry literal source anchors and command scopes; CL-D1 facts contain only
a validated nonnegative integer file count and lowercase SHA-256 digest.
