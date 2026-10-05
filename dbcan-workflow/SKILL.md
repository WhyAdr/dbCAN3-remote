---
name: dbcan-workflow
description: Prepare, run, validate, and report dbCAN 5.2.9 CAZyme analyses from bacterial protein FASTA and Bakta GFF3 inputs, or audit existing dbCAN output directories. Use for explicit-path workflow repair, result validation, multi-family/domain evidence summaries, CGC category overlays, circular-contig checks, and database/runtime preflight.
---

# dbCAN workflow

## Choose the workflow

- For existing results, validate and summarize the exact supplied results directory. Do not rerun searches just to regenerate reports.
- For a new analysis, inventory inputs, environment, database cache, and output destinations first. Keep the input, native results, regenerated diagnostics, and metadata in separate directories.
- Keep supplied native result files unchanged. Treat any result set without a successful stage-status manifest as structurally valid but execution-unattested.

## Use the bundled tools

Run the standard-library test suite from this skill folder before editing workflow code:

```bash
python3 -m unittest discover -s tests -v
```

Prepare a local standalone CDS GFF from a Bakta FAA/GFF3 pair:

```bash
python3 scripts/dbcan_workflow.py prepare \
  --faa /path/to/inputs/original/sample.faa \
  --gff /path/to/inputs/original/sample.gff3 \
  --out-gff /path/to/new/results/sample/inputs/sample.cds.flat.local.gff \
  --report /path/to/new/results/sample/inputs/sample.local_gff_validation.json
```

Review an existing result directory with explicit paths. When a manifest is available, first validate with `--status-file /path/to/metadata/sample/stage_status.json` and omit `--allow-unattested`. A complete attestation binds a run ID, both input hashes, the selected results path, four successful stage exit codes, and the final output inventory. File presence or declared success alone is insufficient.

For an archive without usable attestation, review its table structure using `--allow-unattested`, without supplying the unusable manifest. Record any earlier manifest rejection explicitly. Supplying a failed or incomplete manifest still causes rejection even with this flag; never call a structural review an attested completed run:

```bash
python3 scripts/dbcan_workflow.py validate \
  --faa /path/to/inputs/original/sample.faa \
  --gff /path/to/inputs/original/sample.gff3 \
  --results-dir /path/to/native/results/sample \
  --metadata-dir /path/to/fresh/diagnostics/sample \
  --allow-unattested

python3 scripts/dbcan_workflow.py summarize \
  --faa /path/to/inputs/original/sample.faa \
  --gff /path/to/inputs/original/sample.gff3 \
  --results-dir /path/to/native/results/sample \
  --metadata-dir /path/to/fresh/diagnostics/sample/scientific_summary
```

Summaries derive `sample` from the FAA basename. If several files are named `proteins.faa`, keep explicit isolate directories and identify the isolates in the comparative report; the inferred label is not a sample identity check. The static fixture's `stage_status.template.json` is an unbound test template, not execution evidence.

Audit circular windows separately:

```bash
python3 scripts/audit_circular_windows.py \
  --gff /path/to/inputs/original/sample.gff3 \
  --processed-gff /path/to/native/results/sample/cgc.gff \
  --json /path/to/fresh/diagnostics/sample/circular_audit.json \
  --tsv /path/to/fresh/diagnostics/sample/circular_audit.tsv
```

Inspect `python3 scripts/exact_cgc_categories.py --help` for the overlay's explicit input/output paths. Its `--dbcan-version 5.2.9` is a caller-supplied compatibility guard, not independent runtime evidence; corroborate the historical version from source metadata.

For a new run, pass separate fresh roots and every isolate explicitly. The runner checks input identity, environment paths and versions, CPU allocation, every required stage asset, and the full expected database manifest before it creates result directories. It records argv, stage status, timestamps, resource snapshots, and output hashes. It writes completion metadata only after validation and summary succeed.

```bash
python3 scripts/dbcan_workflow.py run \
  --input-dir /path/to/inputs \
  --results-dir /path/to/fresh/results \
  --metadata-dir /path/to/fresh/metadata \
  --db-dir /path/to/verified/dbcan-databases \
  --expected-manifest /path/to/database.expected.sha256 \
  --env-dir /path/to/dbcan-5.2.9 \
  --samples sample_a sample_b --threads 2 --profile sandbox
```

Use `profiles/sandbox.yaml` or `profiles/hpc.yaml` to choose an explicit thread budget. Pass it to the runner; it refuses requests above the detected CPU allocation. run_dbcan 5.2.9's recorded `substrate_prediction --help` has no `--threads` option, so `scripts/run_dbcan_threadcap.py` caps `os.cpu_count()` only inside that one command. Keep that compatibility shim version-guarded.

## Interpret the evidence

- Keep positive method count, same-family agreement across methods, unique proteins per family, query-aligned HMM/domain instances, and DIAMOND reference-family associations as separate measures.
- Allow one protein to contribute to multiple family and class totals; label these totals as overlapping.
- Treat a DIAMOND family listed on a reference protein as a homology association, not proof that the query has that domain.
- Keep GH0/GT0 and other zero-root labels visible as unresolved evidence, outside resolved-family counts.
- Describe dbCAN substrate and PUL matches as computational predictions. Compare them with protein annotations and neighborhood members before writing substrate-specific claims.
- Record circular topology from the original GFF3. Audit terminal signature windows; do not join across an origin unless the configured signature and null-gene rules support it.
- Use `scripts/exact_cgc_categories.py` to create a version-guarded exact-category overlay in a separate directory. Never overwrite native CGC tables or describe the overlay as an upstream package patch.

## Respect database and runtime boundaries

The validation, report, and fixture tests need only Python's standard library. Do not install dbCAN or fetch databases for those tasks. A new sequence-search run requires the exact stage assets listed in `scripts/dbcan_workflow.py` and must pass `verify-db` against a preserved manifest. The supplied database files are not bundled; the checksum manifest alone does not prove the absent bytes. Explain the database snapshot and reported storage requirement before any new download.

For detailed interpretation, resource, and provenance rules, read `references/reporting.md`, `references/provenance.md`, and the selected profile.
