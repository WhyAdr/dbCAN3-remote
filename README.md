# dbCAN3-remote — dbcan-workflow v0.2.0

`dbcan-workflow/` is a self-contained skill directory with standard-library scripts, tests and fixtures, two operating profiles, a version-pinned package listing, and the recorded database manifest. JN4/JN1B case material and generated reports are outside that folder.

## Test the package

Run these commands from `repository/dbcan-workflow/`:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
bash -n scripts/run_dbcan_workflow.sh
```

The shell entry point is a pass-through to the same explicit-path CLI. Set `DBCAN_PYTHON` to the interpreter selected for the run, for example:

```bash
DBCAN_PYTHON=/path/to/dbcan-5.2.9/bin/python scripts/run_dbcan_workflow.sh validate \
  --faa /path/to/inputs/original/sample.faa \
  --gff /path/to/inputs/original/sample.gff3 \
  --results-dir /path/to/native/results/sample \
  --metadata-dir /path/to/fresh/diagnostics/sample \
  --allow-unattested
```

The suite uses synthetic fixtures and does not need run_dbcan, DIAMOND, Biopython, or a production database.

## Install the skill

The folder is prepared for a skill host that discovers `SKILL.md` with `name: dbcan-workflow`. Follow the current skill-creator instructions in the destination host: stage the complete folder in its required checkout, run its validator, publish/sync through Git, and verify discovery in a fresh session. Do not assume copying a folder activates it. This repository publishes the verified v0.2.0 source. Obtain the `dbcan-workflow/` folder from [WhyAdr/dbCAN3-remote](https://github.com/WhyAdr/dbCAN3-remote) and install it through your host’s supported skill-management workflow. Downloading the source does not activate a skill.

## Provision software for a future new analysis

Use the archived run's Python 3.12.14, Linux x86_64, run_dbcan 5.2.9, and DIAMOND 2.2.8 as the recorded profile. If a new analysis is explicitly needed, create an isolated environment and install the pinned package versions:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r dbcan-workflow/environment/requirements-observed.lock
.venv/bin/run_dbcan version
```

The lock records versions, not wheel hashes. Provide the DIAMOND 2.2.8 binary from a trusted source and check its archive digest against `dbcan-workflow/environment/diamond-linux64-v2.2.8.expected.sha256`. The binary archive was not fetched or checked in this recovery.

The production database is not included. A new database-backed run needs every asset in the preserved 646-entry manifest; the archived README reports about 7.4 GB of database files. That reported size was not remeasured here. Existing-output validation, summary generation, category overlays, circular audits, and the tests need no database. Before a future database download, explain the snapshot and storage requirement, then verify a supplied cache with `scripts/dbcan_workflow.py verify-db`; the workflow has no automatic database-download step.

Use the environment and database preflight before a new analysis, then provide fresh `--results-dir` and `--metadata-dir` values. Never reuse the native result or metadata directories as destinations.

## Verification scope

Thirty standalone workflow tests, seven case-wrapper regressions and fifteen legacy converter tests pass. Fresh-context agents independently reviewed a zero-hit set with rejected provenance and the two native isolate results. Source wrappers in the complete recovery bundle delegate to this canonical package; they need the sibling `repository/` tree and are not standalone files.

The fixture status file is an unbound template. Summaries infer sample names from FAA basenames; preserve isolate directories for identically named inputs. Historical outputs remain execution-unattested. No production environment, database cache or new sequence search was exercised. The detailed completion report and scientific case reports are distributed separately from this public source tree. Do not commit private isolate inputs, native outputs or evaluation case copies to the public repository.
