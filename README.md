# dbCAN3-remote — dbcan-workflow

Prepare, validate, summarize and run **dbCAN 5.2.9** bacterial CAZyme analyses with explicit paths, preserved native results, and evidence-aware reporting. “Remote” means remote **for the human**: the agent runs these tools locally on its own host. The package contains no SSH, network execution, downloader or automatic installer.

Install the complete `dbcan-workflow/` folder using your skill host’s supported Git-backed skill-management workflow. Validate it there and check discovery in a fresh session; downloading the source alone does not activate a skill. See [the agent instructions](dbcan-workflow/SKILL.md).

From a checkout, this quickstart requires only Python’s standard library and the included synthetic fixture:

```bash
cd dbcan-workflow
python3 -B scripts/dbcan_workflow.py describe
python3 -B scripts/dbcan_workflow.py validate \
  --faa tests/fixtures/zero_hit/inputs/sample.faa \
  --gff tests/fixtures/zero_hit/inputs/sample.gff3 \
  --results-dir tests/fixtures/zero_hit/results \
  --metadata-dir /tmp/dbcan-example-diagnostics --allow-unattested
python3 -B -m unittest discover -s tests -v
bash -n scripts/run_dbcan_workflow.sh
python3 -B scripts/gen_docs.py --check
```

Version **0.3.1** adds per-sample append-only event journals, capped failure-log excerpts, and a complete safe preflight check report. Unmet standalone preflight checks return `negative/PREFLIGHT_UNMET`; execution still refuses until every required check passes. Read [Phase 4 diagnostics](dbcan-workflow/references/phase4-diagnostics.md).

The CLI emits one JSON envelope on stdout. Branch on `outcome.kind`; its claim ledger limits what a report may assert. Deliberate refusals include sanctioned remediation. In **0.3.0**, the old stdout payload moves under `result`, with `legacy_status` retained for one release. Strict exit codes are **0 ok, 1 error, 2 usage, 3 refused, 4 negative, 5 failed**. `--exit-policy semantic-zero` (or `DBCAN_WORKFLOW_EXIT_POLICY`) maps ok/negative/refused/failed to 0 while preserving their semantic outcomes. This is a breaking CLI change; see [CHANGELOG](dbcan-workflow/CHANGELOG.md) and [outcome codes](dbcan-workflow/docs/outcome-codes.md).

Existing-output validation, summaries, overlays, circular audits and tests need no production environment or database. A **new search requires user confirmation**, a pinned environment and a separately supplied, fully verified cache. Read [runtime and database provenance](dbcan-workflow/references/provenance.md) before provisioning software or downloading data.

Tests exercise synthetic fixtures and controlled subprocesses. They do not establish that a new HPC or sandbox deployment passes a production database-backed search. Historical case provenance and limitations are preserved in [PROVENANCE](dbcan-workflow/PROVENANCE.md). Private isolate inputs and native results are excluded from this public repository.
