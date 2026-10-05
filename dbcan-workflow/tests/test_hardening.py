"""Regression cases for corrupted tables, output provenance, and runtime selection."""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dbcan_workflow as w
from audit_circular_windows import audit
import run_dbcan_threadcap as threadcap


def write_table(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def mutate(path, field, value):
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header, rows = reader.fieldnames, list(reader)
    rows[0][field] = value
    write_table(path, header, rows)


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dbcan-hardening-")
        self.root = Path(self.temp.name)
        fixture = Path(__file__).parent / "fixtures/zero_hit"
        shutil.copytree(fixture, self.root / "case")
        self.faa = self.root / "case/inputs/sample.faa"
        self.gff = self.root / "case/inputs/sample.gff3"
        self.results = self.root / "case/results"

    def tearDown(self):
        self.temp.cleanup()

    def positive_case(self):
        hmm = {"HMM Name": "GH5.hmm", "HMM Length": "100", "Target Name": "p1", "Target Length": "100",
               "i-Evalue": "1e-30", "HMM From": "1", "HMM To": "90", "Target From": "1", "Target To": "90",
               "Coverage": "0.9", "HMM File Name": "dbCAN.hmm"}
        write_table(self.results / "dbCAN_hmm_results.tsv", w.HMM_HEADER, [hmm])
        overview = dict.fromkeys(w.OVERVIEW_HEADER, "-")
        overview.update({"Gene ID": "p1", "dbCAN_hmm": "GH5(1-90)", "#ofTools": "1"})
        write_table(self.results / "overview.tsv", w.OVERVIEW_HEADER, [overview])
        return hmm, overview

    def validate(self, **kwargs):
        return w.validate_outputs(self.faa, self.gff, self.results, require_stage_status=False, **kwargs)

    def test_overview_labels_and_domains_must_match_raw_records(self):
        self.positive_case()
        for value in ("GH999(1-2)", "GH5(2-90)", "GH5(1-90)+GH5(1-90)"):
            with self.subTest(value=value):
                mutate(self.results / "overview.tsv", "dbCAN_hmm", value)
                with self.assertRaisesRegex(ValueError, "label/domain evidence"):
                    self.validate()

    def test_integer_columns_reject_fractional_and_nonfinite_numbers(self):
        self.positive_case()
        for filename, field, value in (("overview.tsv", "#ofTools", "1.9"),
                                       ("dbCAN_hmm_results.tsv", "Target From", "1.9"),
                                       ("dbCAN_hmm_results.tsv", "Target Length", "100.1")):
            self.positive_case()
            mutate(self.results / filename, field, value)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "invalid integer"):
                self.validate()
        self.assertEqual(w._as_int("1.0", "test", Path("fixture")), 1)
        for value in ("NaN", "Inf", "3.9", "9007199254740993.1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                w._as_int(value, "test", Path("fixture"))

    def test_coverage_and_evalues_require_finite_permitted_values(self):
        for field, value in (("Coverage", "nan"), ("Coverage", "1.1"), ("Coverage", "-0.1"),
                             ("i-Evalue", "inf"), ("i-Evalue", "-1")):
            self.positive_case()
            mutate(self.results / "dbCAN_hmm_results.tsv", field, value)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "invalid numeric"):
                self.validate()

    def test_unknown_stp_and_aggregate_protein_ids_are_rejected(self):
        hmm, _ = self.positive_case()
        hmm["Target Name"] = "UNKNOWN_PROTEIN"
        write_table(self.results / "STP_hmm_results.tsv", w.HMM_HEADER, [hmm])
        with self.assertRaisesRegex(ValueError, "unknown protein"):
            self.validate()
        write_table(self.results / "STP_hmm_results.tsv", w.HMM_HEADER, [])
        row = dict(zip(w.REQUIRED_OUTPUT_HEADERS["total_cgc_info.tsv"],
                       ("model", "100", "UNKNOWN_PROTEIN", "100", "1e-20", "1", "90", "1", "90", "0.9", "STP", "STP")))
        write_table(self.results / "total_cgc_info.tsv", w.REQUIRED_OUTPUT_HEADERS["total_cgc_info.tsv"], [row])
        with self.assertRaisesRegex(ValueError, "unknown accessory protein"):
            self.validate()

    def test_unknown_tc_protein_id_is_rejected(self):
        header = ["TCDB ID", "TCDB Length", "Target ID", "Target Length", "EVALUE", "TCDB START", "TCDB END", "QSTART", "QEND", "COVERAGE", "Database"]
        row = dict(zip(header, ("2.A.1", "100", "UNKNOWN_PROTEIN", "100", "1e-30", "1", "90", "1", "90", "90", "TC")))
        write_table(self.results / "diamond.out.tc", header, [row])
        with self.assertRaisesRegex(ValueError, "unknown accessory protein"):
            self.validate()

    def test_multi_family_diamond_labels_keep_multiplicity_and_unresolved_evidence(self):
        _, overview = self.positive_case()
        diamond = dict(zip(w.DIAMOND_HEADER, ("p1", "ref|GH13_22|GH13_22|GT5|GH0", "50", "90", "0", "0", "1", "90", "1", "90", "1e-30", "100")))
        write_table(self.results / "diamond.out", w.DIAMOND_HEADER, [diamond])
        overview.update({"DIAMOND": "GH13_22+GH13_22+GT5+GH0", "#ofTools": "2"})
        write_table(self.results / "overview.tsv", w.OVERVIEW_HEADER, [overview])
        self.validate()
        summary = w.summarize_results(self.faa, self.gff, self.results, self.root / "metadata")
        self.assertEqual(summary["unique_resolved_family_count"], 3)
        self.assertEqual(summary["candidates_with_unresolved_family_labels"], 1)
        mutate(self.results / "overview.tsv", "DIAMOND", "GH13_22+GT5+GH0")
        with self.assertRaisesRegex(ValueError, "label/domain evidence"):
            self.validate()

    def test_summary_rejects_corruption_before_writing_any_report(self):
        self.positive_case()
        mutate(self.results / "overview.tsv", "dbCAN_hmm", "GH999(1-2)")
        target = self.root / "new_reports"
        with self.assertRaisesRegex(ValueError, "label/domain evidence"):
            w.summarize_results(self.faa, self.gff, self.results, target)
        self.assertFalse(target.exists())

    def status_file(self):
        status = {"run_id": "synthetic-run", "status": "complete", "results_dir": str(self.results),
                  "input_faa_sha256": w.sha256_file(self.faa), "input_gff_sha256": w.sha256_file(self.gff),
                  "stages": {name: {"status": "completed", "exit_code": 0} for name in w.STAGE_NAMES}}
        status["stages"]["substrate_prediction"]["output_sha256"] = w._hash_tree(self.results)
        path = self.root / "status.json"
        path.write_text(json.dumps(status))
        return path

    def test_attestation_binds_outputs_and_cannot_be_bypassed_by_allow_unattested(self):
        status = self.status_file()
        self.assertTrue(self.validate(status_file=status)["execution_attested"])
        (self.results / "PUL_blast.out").write_text("changed archived artifact\n")
        with self.assertRaisesRegex(ValueError, "output hashes differ"):
            self.validate(status_file=status)

    def test_observed_manifest_cannot_overwrite_native_or_input_file(self):
        before = self.faa.read_bytes()
        for target in (self.faa, self.results / "overview.tsv"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "outside native results"):
                self.validate(observed_manifest=target)
        self.assertEqual(before, self.faa.read_bytes())

    def test_normal_symlinked_venv_python_is_used_without_resolving_it(self):
        env = self.root / "venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(env)
        python = env / "bin/python"
        for name, version in (("run_dbcan", "dbCAN version: 5.2.9"), ("diamond", "diamond version 2.2.8")):
            script = env / "bin" / name
            script.write_text(f"#!{python}\nprint({version!r})\n" if name == "run_dbcan"
                              else f"#!/bin/sh\nprintf '%s\\n' '{version}'\n")
            script.chmod(0o755)
        # Give the synthetic environment package metadata for the version probe,
        # without installing or pretending to execute the production application.
        site = next((env / "lib").glob("python*/site-packages"))
        dist = site / "dbcan-5.2.9.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: dbcan\nVersion: 5.2.9\n")
        with patch.object(w, "db_preflight", return_value={"synthetic_database_check": True}):
            result = w.run_preflight(self.faa, self.gff, python, env / "bin/run_dbcan", env / "bin/diamond",
                                     self.root / "unused_db", self.root / "unused_manifest", 1, "sandbox",
                                     self.root / "new_results", self.root / "metadata")
        self.assertEqual(result["python"], str(python))
        self.assertEqual(Path(result["python_prefix"]), env)
        self.assertNotEqual(python.resolve(), python)

    def test_circular_audit_includes_both_endpoints_and_connected_windows(self):
        self.gff.write_text("##gff-version 3\n##sequence-region ctg 1 1000\n"
                            "ctg\tBakta\tregion\t1\t1000\t.\t+\t.\tID=ctg;Is_circular=true\n"
                            "ctg\tBakta\tCDS\t1\t90\t.\t+\t0\tID=first\n"
                            "ctg\tBakta\tCDS\t800\t890\t.\t+\t0\tID=last\n")
        processed = self.results / "cgc.gff"
        processed.write_text("ctg\t.\tCDS\t1\t90\t.\t+\t.\tprotein_id=first;CGC_annotation=CAZyme|GH5\n"
                             "ctg\t.\tCDS\t800\t890\t.\t+\t.\tprotein_id=last;CGC_annotation=TC|2.A.1\n")
        row = audit(self.gff, processed)["contigs"][0]
        self.assertTrue(row["default_wraparound_CGC_indicated"])
        self.assertEqual(set(row["terminal_window_protein_ids"]), {"first", "last"})
        self.assertEqual(len(row["terminal_window_protein_ids"]), 2)

    def test_runner_rejects_parent_traversal_sample_before_writes(self):
        with self.assertRaisesRegex(ValueError, "unique sample names"):
            w.run_workflow(self.root / "inputs", self.root / "fresh_results", self.root / "fresh_metadata",
                           self.root / "db", self.root / "manifest", self.root / "env", [".."], 1, "sandbox")
        self.assertFalse((self.root / "fresh_results").exists())

    def test_derived_adapter_cannot_replace_inputs_or_its_own_report(self):
        before = self.gff.read_bytes()
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            w.prepare_local_gff(self.faa, self.gff, self.gff, self.root / "report.json")
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            w.prepare_local_gff(self.faa, self.gff, self.root / "local.gff", self.root / "local.gff")
        self.assertEqual(self.gff.read_bytes(), before)

    def test_preflight_cannot_place_outputs_inside_database_cache(self):
        with self.assertRaisesRegex(ValueError, "disjoint"):
            w.run_preflight(self.faa, self.gff, self.root / "env/bin/python", self.root / "env/bin/run_dbcan",
                            self.root / "env/bin/diamond", self.root / "db", self.root / "manifest", 1,
                            "sandbox", self.root / "db/results", self.root / "metadata")
        self.assertFalse((self.root / "db").exists())

    def test_circular_region_may_follow_cds_without_changing_validity(self):
        gff = self.root / "order.gff3"
        gff.write_text("##gff-version 3\n##sequence-region ctg 1 1000\n"
                       "ctg\tBakta\tCDS\t950\t1249\t.\t-\t0\tID=p1\n"
                       "ctg\tBakta\tregion\t1\t1000\t.\t+\t.\tID=ctg;Is_circular=true\n")
        self.assertEqual(w.parse_gff(gff)["cds"]["p1"]["end"], 1249)

    def test_real_runner_records_successful_zero_hits_and_failed_stage_separately(self):
        fixture = Path(__file__).parent / "fixtures/zero_hit"
        inputs = self.root / "run_inputs/original"
        inputs.mkdir(parents=True)
        shutil.copy2(self.faa, inputs / "sample.faa")
        shutil.copy2(self.gff, inputs / "sample.gff3")
        manifest = self.root / "expected.sha256"
        manifest.write_text("synthetic reference record\n")
        seed = f"import shutil; shutil.copytree({str(fixture / 'results')!r}, '.', dirs_exist_ok=True)"

        def commands(run_dbcan, faa, local_gff, result_dir, db_dir, threads, log_dir, **kwargs):
            return [(name, [sys.executable, "-c", seed if i == 0 else "pass"], log_dir / f"{i}.log")
                    for i, name in enumerate(w.STAGE_NAMES)]

        preflight = {"database": {"manifest_check": {"snapshot": "synthetic_fixture"}}, "test_fixture": True}
        with patch.object(w, "run_preflight", return_value=preflight), patch.object(w, "stage_commands", side_effect=commands):
            result = w.run_workflow(inputs.parent, self.root / "run_results", self.root / "run_metadata",
                                    self.root / "db", manifest, self.root / "env", ["sample"], 1, "sandbox")
        self.assertEqual(result["status"], "complete")
        status = self.root / "run_metadata/sample/stage_status.json"
        output = self.root / "run_results/sample"
        validation = w.validate_outputs(inputs / "sample.faa", inputs / "sample.gff3", output,
                                        status_file=status, require_stage_status=True)
        self.assertEqual(validation["overview_candidates"], 0)
        self.assertTrue((self.root / "run_metadata/sample/completion.json").exists())

        def failing(*args, **kwargs):
            log_dir = args[6]
            return [(name, [sys.executable, "-c", "raise SystemExit(7)" if i == 1 else "pass"], log_dir / f"{i}.log")
                    for i, name in enumerate(w.STAGE_NAMES)]
        with patch.object(w, "run_preflight", return_value=preflight), patch.object(w, "stage_commands", side_effect=failing):
            failure = w.run_workflow(inputs.parent, self.root / "failed_results", self.root / "failed_metadata",
                                     self.root / "db", manifest, self.root / "env", ["sample"], 1, "sandbox")
        self.assertEqual(failure["status"], "failed")
        ledger = json.loads((self.root / "failed_metadata/sample/stage_status.json").read_text())
        self.assertEqual(ledger["stages"]["gff_process"]["exit_code"], 7)
        self.assertEqual(ledger["stages"]["substrate_prediction"]["status"], "skipped")
        self.assertFalse((self.root / "failed_metadata/sample/completion.json").exists())
