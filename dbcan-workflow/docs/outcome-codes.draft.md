# Baseline raise-site inventory

Baseline: `0b1bcc0`. Every explicit raise/exit is listed below; implicit I/O failures and programming defects remain INTERNAL_ERROR at the boundary. Sites refer to baseline lines, not the evolving source.

Classification follows the supplied plan: paths, environment and identity preconditions refuse; read data content is negative; external execution is failed. The internal thread-cap shim preserves its SystemExit checks; its parent runner classifies nonzero subprocess exits as STAGE_FAILED.

Maintainer review: the implementation request authorizes proceeding with the supplied classification rules; this reviewable table is committed before typed conversion. No guards are relaxed. Refusals use the central registry remediation and forbidden actions.

| Site | Function | Exception | Kind | Code | Original expression |
|---|---|---|---|---|---|
| `audit_circular_windows.py:44` | `audit` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"processed GFF CDS ID set differs from input; missing={len(set(annotation['cds'])-seen)}")` |
| `audit_circular_windows.py:25` | `audit` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"expected 9 GFF columns at {processed_gff}:{line_no}")` |
| `audit_circular_windows.py:31` | `audit` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"missing or duplicate processed protein ID at {processed_gff}:{line_no}")` |
| `audit_circular_windows.py:34` | `audit` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown processed protein ID {pid!r}")` |
| `audit_circular_windows.py:39` | `audit` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"processed coordinates differ for {pid}: {observed} != {expected}")` |
| `dbcan_workflow.py:122` | `read_tsv` | FileNotFoundError | refused | `INPUT_MISSING` | `FileNotFoundError(f"required result file is missing: {path}")` |
| `dbcan_workflow.py:154` | `parse_fasta` | FileNotFoundError | refused | `INPUT_MISSING` | `FileNotFoundError(f"protein FASTA is missing: {path}")` |
| `dbcan_workflow.py:188` | `parse_fasta` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"no FASTA records in {path}")` |
| `dbcan_workflow.py:194` | `parse_gff` | FileNotFoundError | refused | `INPUT_MISSING` | `FileNotFoundError(f"GFF3 is missing: {path}")` |
| `dbcan_workflow.py:270` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"no CDS features found in {path}")` |
| `dbcan_workflow.py:285` | `compare_faa_gff` | ValueError | refused | `INPUT_MISMATCH` | `ValueError(f"FAA/GFF CDS IDs differ; cds_only={missing_from_faa[:10]}, faa_only={faa_only[:10]}")` |
| `dbcan_workflow.py:287` | `compare_faa_gff` | ValueError | refused | `INPUT_MISMATCH` | `ValueError("FAA/GFF record counts differ despite matching ID sets")` |
| `dbcan_workflow.py:371` | `parse_sha256_manifest` | ValueError | refused | `MANIFEST_PATH_UNSAFE` | `ValueError(f"empty checksum manifest: {path}")` |
| `dbcan_workflow.py:379` | `verify_database` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("expected manifest must be outside the database directory")` |
| `dbcan_workflow.py:418` | `db_preflight` | FileNotFoundError | refused | `DB_UNVERIFIED` | `FileNotFoundError(f"database assets missing by stage under {db_dir}: {missing_by_stage}")` |
| `dbcan_workflow.py:421` | `db_preflight` | ValueError | refused | `DB_UNVERIFIED` | `ValueError(f"database directory does not match pinned {SNAPSHOT}: missing={len(manifest_check['missing'])}, unexpected={len(manifest_check['unexpected'])}, mismatched={len(manifest_check['mismatched'])}")` |
| `dbcan_workflow.py:573` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError(f"stage status manifest is marked {data.get('status')!r}: {status_file}")` |
| `dbcan_workflow.py:591` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError(f"one or more required stages are incomplete or unsuccessful: {problems}")` |
| `dbcan_workflow.py:606` | `validate_outputs` | FileNotFoundError | refused | `RESULTS_DIR_MISSING` | `FileNotFoundError(f"results directory does not exist: {results_dir}")` |
| `dbcan_workflow.py:612` | `validate_outputs` | FileNotFoundError | negative | `STRUCTURE_INVALID` | `FileNotFoundError(f"missing required outputs in {results_dir}: {missing}")` |
| `dbcan_workflow.py:617` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError("overview.tsv contains an empty Gene ID")` |
| `dbcan_workflow.py:619` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError("overview.tsv contains duplicate protein IDs")` |
| `dbcan_workflow.py:622` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"overview.tsv contains unknown protein IDs: {unknown_overview[:10]}")` |
| `dbcan_workflow.py:666` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"overview IDs disagree with method tables; overview_only={extra[:10]}, method_only={absent[:10]}")` |
| `dbcan_workflow.py:670` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"uniInput.faa ID set differs from source FAA; missing={sorted(set(proteins)-set(processed_faa))[:10]}, extra={sorted(set(processed_faa)-set(proteins))[:10]}")` |
| `dbcan_workflow.py:703` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"cgc.gff CDS IDs differ from source GFF; missing={sorted(set(expected_cds)-set(cgc_gff_rows))[:10]}, extra={sorted(set(cgc_gff_rows)-set(expected_cds))[:10]}")` |
| `dbcan_workflow.py:739` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CGC IDs differ between member table and summary; member_only={sorted(set(by_cluster)-set(summary_by_id))}, summary_only={sorted(set(summary_by_id)-set(by_cluster))}")` |
| `dbcan_workflow.py:812` | `summarize_results` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("summary output directory must be separate from and outside the native results directory")` |
| `dbcan_workflow.py:1039` | `check_fresh_destinations` | FileExistsError | refused | `PATHS_OVERLAP` | `FileExistsError(f"metadata destination is not empty; choose a new --metadata-dir: {metadata_root}")` |
| `dbcan_workflow.py:1046` | `run_preflight` | ValueError | refused | `ENV_UNMET` | `ValueError("threads must be a positive integer")` |
| `dbcan_workflow.py:1048` | `run_preflight` | ValueError | refused | `ENV_UNMET` | `ValueError("profile must be sandbox or hpc")` |
| `dbcan_workflow.py:1054` | `run_preflight` | ValueError | refused | `THREADS_EXCEED_ALLOCATION` | `ValueError(
            f"requested threads={threads} exceeds detected CPU allocation "
            f"{resources['effective_cpu_allocation']}"
        )` |
| `dbcan_workflow.py:1066` | `run_preflight` | ValueError | refused | `ENV_UNMET` | `ValueError("Python, run_dbcan, and DIAMOND must be selected from one environment bin directory")` |
| `dbcan_workflow.py:1077` | `run_preflight` | RuntimeError | refused | `ENV_UNMET` | `RuntimeError(f"selected Python smoke test failed: {python_probe.stderr.strip()}")` |
| `dbcan_workflow.py:1080` | `run_preflight` | ValueError | refused | `ENV_UNMET` | `ValueError("selected Python environment identity or dbcan distribution version differs from the requested environment")` |
| `dbcan_workflow.py:1083` | `run_preflight` | RuntimeError | refused | `ENV_UNMET` | `RuntimeError(f"run_dbcan version probe failed or was not 5.2.9: {(run_probe.stdout + run_probe.stderr).strip()}")` |
| `dbcan_workflow.py:1086` | `run_preflight` | RuntimeError | refused | `ENV_UNMET` | `RuntimeError(f"DIAMOND version probe failed or was not 2.2.8: {(diamond_probe.stdout + diamond_probe.stderr).strip()}")` |
| `dbcan_workflow.py:1155` | `_guard_output_files` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("derived output files must be distinct and must not overwrite source files")` |
| `dbcan_workflow.py:1187` | `run_workflow` | ValueError | refused | `SAMPLE_ID_UNSAFE` | `ValueError("provide unique sample names containing only letters, digits, period, underscore, or hyphen")` |
| `dbcan_workflow.py:1195` | `run_workflow` | FileNotFoundError | refused | `INPUT_MISSING` | `FileNotFoundError(f"input directory does not exist: {input_dir}")` |
| `dbcan_workflow.py:127` | `read_tsv` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unexpected TSV header in {path}: {header!r}; expected {expected_header!r}")` |
| `dbcan_workflow.py:129` | `read_tsv` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"TSV has no header: {path}")` |
| `dbcan_workflow.py:133` | `read_tsv` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"malformed TSV row {n} in {path}")` |
| `dbcan_workflow.py:143` | `parse_attributes` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"GFF3 attribute lacks '=': {item!r}")` |
| `dbcan_workflow.py:147` | `parse_attributes` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate GFF3 attribute key {key!r}")` |
| `dbcan_workflow.py:165` | `flush` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"empty FASTA sequence for {current!r} in {path} near line {line_no}")` |
| `dbcan_workflow.py:167` | `flush` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate protein ID {current!r} in {path}")` |
| `dbcan_workflow.py:169` | `flush` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid FASTA sequence symbols for {current!r} in {path}")` |
| `dbcan_workflow.py:291` | `compare_faa_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"missing ##sequence-region length for contig {feature['seqid']!r}")` |
| `dbcan_workflow.py:362` | `parse_sha256_manifest` | ValueError | refused | `MANIFEST_PATH_UNSAFE` | `ValueError(f"malformed SHA256 manifest row at {path}:{line_no}")` |
| `dbcan_workflow.py:366` | `parse_sha256_manifest` | ValueError | refused | `MANIFEST_PATH_UNSAFE` | `ValueError(f"unsafe path in checksum manifest: {rel!r}")` |
| `dbcan_workflow.py:368` | `parse_sha256_manifest` | ValueError | refused | `MANIFEST_PATH_UNSAFE` | `ValueError(f"duplicate path in checksum manifest: {rel}")` |
| `dbcan_workflow.py:383` | `verify_database` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("observed manifest must be outside the database directory and must not overwrite the expected manifest")` |
| `dbcan_workflow.py:442` | `_as_int` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError("value is not a finite integer")` |
| `dbcan_workflow.py:445` | `_as_int` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid integer {label}={value!r} in {path}")` |
| `dbcan_workflow.py:453` | `_as_number` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError("number is outside the permitted finite range")` |
| `dbcan_workflow.py:456` | `_as_number` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid numeric {label}={value!r} in {path}")` |
| `dbcan_workflow.py:463` | `_check_domain_rows` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown protein {pid!r} at {path}:{n}")` |
| `dbcan_workflow.py:467` | `_check_domain_rows` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"Target Length {tlen} differs from FASTA length {actual_len} for {pid} in {path}:{n}")` |
| `dbcan_workflow.py:474` | `_check_domain_rows` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid query domain bounds {qstart}-{qend}/{actual_len} for {pid} in {path}:{n}")` |
| `dbcan_workflow.py:476` | `_check_domain_rows` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid HMM bounds {hstart}-{hend}/{hlen} for {pid} in {path}:{n}")` |
| `dbcan_workflow.py:480` | `_check_domain_rows` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"empty subfamily name in {path}:{n}")` |
| `dbcan_workflow.py:518` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown accessory protein {pid!r} in {path}:{n}")` |
| `dbcan_workflow.py:521` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"accessory target length differs for {pid}")` |
| `dbcan_workflow.py:528` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid accessory domain bounds for {pid} in {path}:{n}")` |
| `dbcan_workflow.py:530` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown accessory category {row['Type']!r} in {path}:{n}")` |
| `dbcan_workflow.py:568` | `_status_check` | ValueError | refused | `ATTESTATION_REQUIRED` | `ValueError(f"stage completion evidence is missing: {status_file}")` |
| `dbcan_workflow.py:576` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError(f"stage status manifest lacks a run ID: {status_file}")` |
| `dbcan_workflow.py:583` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError(f"stage status manifest results path does not match the selected results directory: {status_file}")` |
| `dbcan_workflow.py:595` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError("stage status manifest lacks final output hash evidence")` |
| `dbcan_workflow.py:597` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError("stage status manifest output hashes differ from the selected results")` |
| `dbcan_workflow.py:633` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown DIAMOND protein ID {pid!r} in diamond.out:{n}")` |
| `dbcan_workflow.py:637` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid DIAMOND query bounds for {pid} at diamond.out:{n}")` |
| `dbcan_workflow.py:654` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"#ofTools={reported} but {actual} method columns are positive for {pid}")` |
| `dbcan_workflow.py:673` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"sequence changed between input FAA and uniInput.faa for {pid}")` |
| `dbcan_workflow.py:712` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"empty CGC# or Protein ID at cgc_standard_out.tsv:{n}")` |
| `dbcan_workflow.py:715` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate CGC member {pid} in {cid}")` |
| `dbcan_workflow.py:718` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown CGC member protein ID {pid}")` |
| `dbcan_workflow.py:724` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CGC membership coordinates differ from source for {pid}: {tup} != {expected_tuple}")` |
| `dbcan_workflow.py:726` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CGC annotation differs between cgc.gff and membership table for {pid}")` |
| `dbcan_workflow.py:730` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CGC gene type differs from annotation categories for {pid}")` |
| `dbcan_workflow.py:736` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"empty or duplicate CGC ID in summary: {cid!r}")` |
| `dbcan_workflow.py:745` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"inconsistent contig membership for {cid}")` |
| `dbcan_workflow.py:764` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"substrate row references unknown CGC {cgcid!r}")` |
| `dbcan_workflow.py:766` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate substrate row for {cgcid}")` |
| `dbcan_workflow.py:798` | `validate_outputs` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("observed result manifest must not overwrite stage status")` |
| `dbcan_workflow.py:815` | `summarize_results` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("summary metadata must be separate from the input directory")` |
| `dbcan_workflow.py:1037` | `check_fresh_destinations` | FileExistsError | refused | `PATHS_OVERLAP` | `FileExistsError(f"results destination is not empty; choose a new --results-dir: {target}")` |
| `dbcan_workflow.py:1060` | `run_preflight` | FileNotFoundError | refused | `ENV_UNMET` | `FileNotFoundError(f"selected {label} executable is not executable: {path}")` |
| `dbcan_workflow.py:1193` | `run_workflow` | ValueError | refused | `PATHS_OVERLAP` | `ValueError(f"{left_name} and {right_name} directories must be disjoint: {left}, {right}")` |
| `dbcan_workflow.py:1199` | `run_workflow` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("run outputs must not overlap the expected database manifest")` |
| `dbcan_workflow.py:1202` | `run_workflow` | FileExistsError | refused | `PATHS_OVERLAP` | `FileExistsError(f"run destination must be fresh and empty: {root}")` |
| `dbcan_workflow.py:238` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"expected 9 GFF3 columns at {path}:{line_no}, found {len(cols)}")` |
| `dbcan_workflow.py:247` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CDS without ID at {path}:{line_no}")` |
| `dbcan_workflow.py:249` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate CDS ID {pid!r} in {path}")` |
| `dbcan_workflow.py:252` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid coordinates for {pid} at {path}:{line_no}")` |
| `dbcan_workflow.py:254` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid strand {strand!r} for {pid} at {path}:{line_no}")` |
| `dbcan_workflow.py:256` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid CDS phase {phase!r} for {pid} at {path}:{line_no}")` |
| `dbcan_workflow.py:295` | `compare_faa_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"linear contig {feature['seqid']} has CDS {pid} ending beyond length {length}")` |
| `dbcan_workflow.py:298` | `compare_faa_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CDS {pid} exceeds one circular contig traversal")` |
| `dbcan_workflow.py:544` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unexpected accessory header in {path}")` |
| `dbcan_workflow.py:547` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown accessory protein {pid!r} in {path}:{n}")` |
| `dbcan_workflow.py:550` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"accessory target length differs for {pid} in {path}")` |
| `dbcan_workflow.py:554` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid accessory query bounds for {pid} in {path}:{n}")` |
| `dbcan_workflow.py:559` | `_check_accessory_tables` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid accessory reference bounds for {pid} in {path}:{n}")` |
| `dbcan_workflow.py:579` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError(f"stage status manifest lacks {label} identity evidence: {status_file}")` |
| `dbcan_workflow.py:581` | `_status_check` | ValueError | refused | `ATTESTATION_REJECTED` | `ValueError(f"stage status manifest {label} hash does not match the selected input: {status_file}")` |
| `dbcan_workflow.py:644` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid DIAMOND {field} for {pid}")` |
| `dbcan_workflow.py:657` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"overview says {pid} has a {col} hit but the corresponding result table has none")` |
| `dbcan_workflow.py:659` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"{col} result table contains {pid}, but overview has no {col} call")` |
| `dbcan_workflow.py:661` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"overview {col} label/domain evidence differs from raw results for {pid}")` |
| `dbcan_workflow.py:684` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"cgc.gff row does not have 9 columns at line {n}")` |
| `dbcan_workflow.py:690` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"cgc.gff CDS lacks protein_id/ID at line {n}")` |
| `dbcan_workflow.py:692` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate processed GFF protein ID {pid}")` |
| `dbcan_workflow.py:694` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unknown processed GFF protein ID {pid}")` |
| `dbcan_workflow.py:699` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"contig/coordinate/strand changed for {pid}: {observed_tuple} != {expected_tuple}")` |
| `dbcan_workflow.py:756` | `validate_outputs` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"{cid} summary {key}={observed}, member rows imply {expected}")` |
| `dbcan_workflow.py:796` | `validate_outputs` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("observed result manifest must be outside native results and input directories")` |
| `dbcan_workflow.py:1148` | `_guard_output_directories` | ValueError | refused | `PATHS_OVERLAP` | `ValueError(f"output directories must be disjoint from inputs, runtime, database and each other: {left}; {right}")` |
| `dbcan_workflow.py:1360` | `main` | ValueError | refused | `PATHS_OVERLAP` | `ValueError("results and metadata directories must be disjoint")` |
| `dbcan_workflow.py:180` | `parse_fasta` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"empty FASTA header at {path}:{line_no}")` |
| `dbcan_workflow.py:212` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"conflicting topology declarations for {cols[0]}")` |
| `dbcan_workflow.py:224` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"malformed sequence-region directive at {path}:{line_no}")` |
| `dbcan_workflow.py:227` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"invalid sequence-region bounds at {path}:{line_no}")` |
| `dbcan_workflow.py:229` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"conflicting sequence-region length for {seqid!r}")` |
| `dbcan_workflow.py:261` | `parse_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"out-of-range CDS {pid} is not a valid single-wrap circular interval")` |
| `dbcan_workflow.py:322` | `prepare_local_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"unexpected CDS while preparing local GFF: {attrs.get('ID')}")` |
| `dbcan_workflow.py:1266` | `run_workflow` | RuntimeError | failed | `STAGE_FAILED` | `RuntimeError(f"{sample} {stage} failed with exit code {completed.returncode}; see {log_file}")` |
| `dbcan_workflow.py:184` | `parse_fasta` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"sequence before first FASTA header at {path}:{line_no}")` |
| `dbcan_workflow.py:1260` | `run_workflow` | re-raise | failed | `STAGE_FAILED` | `raise` |
| `dbcan_workflow.py:1372` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit(2)` |
| `dbcan_workflow.py:1383` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit(2)` |
| `exact_cgc_categories.py:76` | `identify_clusters` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError("additional_logic must be all or any")` |
| `exact_cgc_categories.py:154` | `rebuild` | ValueError | refused | `VERSION_UNSUPPORTED` | `ValueError(f"exact-category compatibility rebuild is version-guarded for dbCAN {SUPPORTED_VERSION}; got {installed_version}")` |
| `exact_cgc_categories.py:53` | `read_processed_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"expected 9 columns in {path}:{line_no}")` |
| `exact_cgc_categories.py:59` | `read_processed_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"no protein_id/ID in {path}:{line_no}")` |
| `exact_cgc_categories.py:61` | `read_processed_gff` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"duplicate protein ID in processed GFF: {pid}")` |
| `exact_cgc_categories.py:140` | `summary_rows` | ValueError | negative | `STRUCTURE_INVALID` | `ValueError(f"CGC spans multiple contigs: {cid}")` |
| `run_dbcan_threadcap.py:74` | `<module>` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit(main())` |
| `run_dbcan_threadcap.py:22` | `cap_os_cpu_count` | ValueError | refused | `ENV_UNMET` | `ValueError("CPU budget must be positive")` |
| `run_dbcan_threadcap.py:31` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit("usage: run_dbcan_threadcap.py THREADS <run_dbcan subcommand and options>")` |
| `run_dbcan_threadcap.py:34` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit("THREADS must be a positive integer")` |
| `run_dbcan_threadcap.py:41` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit(f"CPU-count compatibility wrapper is tested only for dbcan {SUPPORTED_VERSION}; found {version}")` |
| `run_dbcan_threadcap.py:43` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit("a run_dbcan subcommand is required")` |
| `run_dbcan_threadcap.py:45` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit("use a native --threads option instead of the compatibility wrapper when available")` |
| `run_dbcan_threadcap.py:49` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit(f"expected one run_dbcan console entry point, found {len(candidates)}")` |
| `run_dbcan_threadcap.py:39` | `main` | SystemExit | projection | `EXIT_PROJECTION` | `SystemExit("dbcan is not installed in the selected Python environment")` |
