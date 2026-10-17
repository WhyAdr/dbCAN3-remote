# Baseline verification (0b1bcc0)

`python3 -B -m unittest discover -s tests -q`: Ran 30 tests; OK.

`sha256sum -c FILES.sha256`: original manifest passes before source edits.

## Probe A

Exit 1; stdout 0 bytes.

```text

Traceback (most recent call last):
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 1388, in <module>
    main()
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 1360, in main
    raise ValueError("results and metadata directories must be disjoint")
ValueError: results and metadata directories must be disjoint

```

## Probe B

Exit 1; stdout 0 bytes.

```text

Traceback (most recent call last):
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 1388, in <module>
    main()
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 1363, in main
    data = validate_outputs(r.faa, r.gff, results_dir, status_file=r.status_file,
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 769, in validate_outputs
    status = _status_check(status_file, require_stage_status, faa=faa, gff=gff, results_dir=results_dir)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 568, in _status_check
    raise ValueError(f"stage completion evidence is missing: {status_file}")
ValueError: stage completion evidence is missing: None

```

## Probe C

Exit 1; stdout 0 bytes.

```text

Traceback (most recent call last):
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 1388, in <module>
    main()
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 1363, in main
    data = validate_outputs(r.faa, r.gff, results_dir, status_file=r.status_file,
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/scripts/dbcan_workflow.py", line 606, in validate_outputs
    raise FileNotFoundError(f"results directory does not exist: {results_dir}")
FileNotFoundError: results directory does not exist: /tmp/dbcan-baseline-wmsskpfs/missing

```

## Probe D

Exit 2; stdout 0 bytes.

```text

usage: dbcan_workflow.py validate [-h] --faa FAA --gff GFF --results-dir
                                  RESULTS_DIR --metadata-dir METADATA_DIR
                                  [--status-file STATUS_FILE]
                                  [--allow-unattested]
                                  [--observed-manifest OBSERVED_MANIFEST]
dbcan_workflow.py validate: error: the following arguments are required: --gff, --results-dir, --metadata-dir

```

## Probe E

Exit 2; stdout 24171 bytes.

```text
{
  "snapshot": "db_v5-2-9_5-5-2026",
  "expected_manifest": "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/environment/database_v5-2-9_5-5-2026.expected.sha256",
  "expected_manifest_sha256": "0f20c1986c32df59723cffc20b677789ed0c12819cd0939e16788f58dea406d2",
  "expected_file_count": 646,
  "observed_file_count": 0,
  "missing": [
    "CAZy.dmnd",
    "PUL.dmnd",
    "STP.hmm",
    "TCDB.dmnd",
    "TF.dmnd",
    "TF.hmm",
    "dbCAN-PUL.xlsx",
    "dbCAN-PUL/PUL0001.out/cgc.gff",
    "dbCAN-PUL/PUL0002.out/cgc.gff",
    "dbCAN-PUL/PUL0003.out/cgc.gff",
    "dbCAN-PUL/PUL0004.out/cgc.gff",
    "dbCAN-PUL/PUL0005.out/cgc.gff",
    "dbCAN-PUL/PUL0006.out/cgc.gff",
    "dbCAN-PUL/PUL0007.out/cgc.gff",
    "dbCAN-PUL/PUL0008.out/cgc.gff",
    "dbCAN-PUL/PUL0009.out/cgc.gff",
    "dbCAN-PUL/PUL0010.out/cgc.gff",
    "dbCAN-PUL/PUL0012.out/cgc.gff",
    "dbCAN-PUL/PUL0014.out/cgc.gff",
    "dbCAN-PUL/PUL0015.out/cgc.gff",
    "dbCAN-PUL/PUL0016.out/cgc.gff",
    "dbCAN-PUL/PUL0017.out/cgc.gff",
    "dbCAN-PUL/PUL0018.out/cgc.gff",
    "dbCAN-PUL/PUL0019.out/cgc.gff",
    "dbCAN-PUL/PUL0020.out/cgc.gff",
    "dbCAN-PUL/PUL0021.out/cgc.gff",
    "dbCAN-PUL/PUL0022.out/cgc.gff",
    "dbCAN-PUL/PUL0023.out/cgc.gff",
    "dbCAN-PUL/PUL0024.out/cgc.gff",
    "dbCAN-PUL/PUL0026.out/cgc.gff",
    "dbCAN-PUL/PUL0027.out/cgc.gff",
    "dbCAN-PUL/PUL0028.out/cgc.gff",
    "dbCAN-PUL/PUL0029.out/cgc.gff",
    "dbCAN-PUL/PUL0030.out/cgc.gff",
    "dbCAN-PUL/PUL0031.out/cgc.gff",
    "dbCAN-PUL/PUL0032.out/cgc.gff",
    "dbCAN-PUL/PUL0033.out/cgc.gff",
    "dbCAN-PUL/PUL0034.out/cgc.gff",
    "dbCAN-PUL/PUL0035.out/cgc.gff",
    "dbCAN-PUL/PUL0037.out/cgc.gff",
    "dbCAN-PUL/PUL0038.out/cgc.gff",
    "dbCAN-PUL/PUL0039.out/cgc.gff",
    "dbCAN-PUL/PUL0040.out/cgc.gff",
    "dbCAN-PUL/PUL0041.out/cgc.gff",
    "dbCAN-PUL/PUL0042.out/cgc.gff",
    "dbCAN-PUL/PUL0044.out/cgc.gff",
    "dbCAN-PUL/PUL0044.out/uniInput.gff",
    "dbCAN-PUL/PUL0045.out/cgc.gff",
    "dbCAN-PUL/PUL0048.out/cgc.gff",
    "dbCAN-PUL/PUL0049.out/cgc.gff",
    "dbCAN-PUL/PUL0050.out/cgc.gff",
    "dbCAN-PUL/PUL0051.out/cgc.gff",
    "dbCAN-PUL/PUL0052.out/cgc.gff",
    "dbCAN-PUL/PUL0053.out/cgc.gff",
    "dbCAN-PUL/PUL0054.out/cgc.gff",
    "dbCAN-PUL/PUL0055.out/cgc.gff",
    "dbCAN-PUL/PUL0056.out/cgc.gff",
    "dbCAN-PUL/PUL0058.out/cgc.gff",
    "dbCAN-PUL/PUL0063.out/cgc.gff",
    "dbCAN-PUL/PUL0064.out/cgc.gff",
    "dbCAN-PUL/PUL0065.out/cgc.gff",
    "dbCAN-PUL/PUL0066.out/cgc.g

```

## Probe F

Exit 2; stdout 0 bytes.

```text

Set DBCAN_PYTHON to the selected environment interpreter.
Usage: DBCAN_PYTHON=/path/to/env/bin/python scripts/run_dbcan_workflow.sh run --input-dir ...

```

## Probe G

Exit 0; stdout 815 bytes.

```text
{
  "cgc_count": 0,
  "cgc_member_rows": 0,
  "circular_contigs": 0,
  "execution_attested": false,
  "faa_proteins": 1,
  "gff_cds": 1,
  "input_faa_sha256": "eb76c0a3f0d6a632aefa13c1c4b185c255e6ca543558b6b9be1e5e5288028b01",
  "input_gff_sha256": "85c11736ef0c4cec8c19e9f5f94fdab050dc848e10778b804cd0b156fe53e049",
  "method_count_distribution": {},
  "method_hit_proteins": {
    "DIAMOND": 0,
    "dbCAN-HMM": 0,
    "dbCAN-sub": 0
  },
  "origin_spanning_cds": [],
  "overview_candidates": 0,
  "positive_in_two_or_more_methods": 0,
  "pseudogene_cds_count": 0,
  "resolved_family_agreement": 0,
  "results_dir": "/workspace/scratch/51b8ca04e32d/dbCAN3-remote/dbcan-workflow/tests/fixtures/zero_hit/results",
  "sample": "sample",
  "status": "structurally_valid_execution_unattested",
  "substrate_rows": 0
}


```
