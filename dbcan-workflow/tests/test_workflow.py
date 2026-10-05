from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dbcan_workflow as workflow  # noqa: E402
from exact_cgc_categories import categories, gene_type, identify_clusters  # noqa: E402
import run_dbcan_threadcap as threadcap  # noqa: E402


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dbcan-skill-test-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_family_parser_retains_secondary_labels_and_unresolved_roots(self) -> None:
        self.assertEqual(workflow.parse_family_roots("CE4_e289+GH153_e4+GH153_e4+GT5"),
                         {"CE4", "GH153", "GT5"})
        self.assertEqual(workflow.parse_family_roots("GH0+GT0"), set())

    def test_bakta_preparation_preserves_circular_cds_and_pseudogene_flags(self) -> None:
        faa = self.root / "input.faa"
        gff = self.root / "input.gff3"
        output = self.root / "prepared" / "input.local.gff"
        report = self.root / "metadata" / "input.validation.json"
        faa.write_text(">p1\n" + "A" * 100 + "\n")
        gff.write_text(
            "##gff-version 3\n##sequence-region ctg 1 1000\n"
            "ctg\tBakta\tregion\t1\t1000\t.\t+\t.\tID=ctg;Is_circular=true\n"
            "ctg\tBakta\tCDS\t950\t1249\t.\t-\t0\tID=p1;Parent=gene1;pseudo=true;Name=pseudogene\n")
        data = workflow.prepare_local_gff(faa, gff, output, report)
        prepared = output.read_text()
        self.assertNotIn("Parent=", prepared)
        self.assertIn("pseudo=true", prepared)
        self.assertEqual(data["origin_spanning_cds"][0]["protein_id"], "p1")
        self.assertEqual(data["contigs"][0]["is_circular"], True)

    def test_exact_category_does_not_accept_tf_member_name_as_tc(self) -> None:
        self.assertEqual(categories("TF|GLTC_BACSU"), {"TF"})
        self.assertEqual(gene_type("TF|GLTC_BACSU"), "TF")
        genes = [
            {"contig": "c", "start": 100, "end": 199, "protein_id": "core",
             "annotation": "CAZyme|GH5", "categories": {"CAZyme"}},
            {"contig": "c", "start": 300, "end": 399, "protein_id": "tf",
             "annotation": "TF|GLTC_BACSU", "categories": categories("TF|GLTC_BACSU")},
            {"contig": "c", "start": 500, "end": 599, "protein_id": "null",
             "annotation": "null", "categories": {"null"}},
        ]
        self.assertEqual(identify_clusters({"c": genes}), [])
        genes[1]["annotation"] = "TC|2.A.1"
        genes[1]["categories"] = categories(genes[1]["annotation"])
        clusters = identify_clusters({"c": genes})
        self.assertEqual([[g["protein_id"] for g in c] for c in clusters], [["core", "tf"]])

    def test_summary_keeps_multi_family_evidence_and_correct_candidate_agreement(self) -> None:
        input_dir = self.root / "inputs" / "original"
        result_dir = self.root / "results" / "sample"
        output_dir = self.root / "metadata" / "sample"
        input_dir.mkdir(parents=True)
        result_dir.mkdir(parents=True)
        (input_dir / "sample.faa").write_text(">p1\n" + "A" * 100 + "\n>p2\n" + "G" * 60 + "\n")
        (input_dir / "sample.gff3").write_text(
            "##gff-version 3\n##sequence-region ctg 1 1000\n"
            "ctg\tBakta\tregion\t1\t1000\t.\t+\t.\tID=ctg;Is_circular=true\n"
            "ctg\tBakta\tCDS\t100\t399\t.\t+\t0\tID=p1\n"
            "ctg\tBakta\tCDS\t500\t679\t.\t-\t0\tID=p2\n")
        self._write_tsv(result_dir / "overview.tsv", workflow.OVERVIEW_HEADER, [
            {"Gene ID": "p1", "EC#": "-", "dbCAN_hmm": "CE4_e289", "dbCAN_sub": "GH153_e4",
             "DIAMOND": "GH153+CE4", "#ofTools": "3", "Recommend Results": "GH153_e4", "Substrate": "-"},
            {"Gene ID": "p2", "EC#": "-", "dbCAN_hmm": "GH5_e1", "dbCAN_sub": "-",
             "DIAMOND": "-", "#ofTools": "1", "Recommend Results": "GH5_e1", "Substrate": "-"},
        ])
        self._write_tsv(result_dir / "dbCAN_hmm_results.tsv", workflow.HMM_HEADER, [
            {"HMM Name": "CE4_e289", "HMM Length": "100", "Target Name": "p1", "Target Length": "100",
             "i-Evalue": "1e-30", "HMM From": "1", "HMM To": "90", "Target From": "1", "Target To": "90",
             "Coverage": "0.9", "HMM File Name": "dbCAN.hmm"},
            {"HMM Name": "GH5_e1", "HMM Length": "100", "Target Name": "p2", "Target Length": "60",
             "i-Evalue": "1e-20", "HMM From": "1", "HMM To": "60", "Target From": "1", "Target To": "60",
             "Coverage": "0.6", "HMM File Name": "dbCAN.hmm"},
        ])
        self._write_tsv(result_dir / "dbCANsub_hmm_results.tsv", workflow.SUBFAM_HEADER, [
            {"Subfam Name": "GH153_e4", "Subfam Composition": "GH153", "Subfam EC": "-", "Substrate": "-",
             "HMM Length": "100", "Target Name": "p1", "Target Length": "100", "i-Evalue": "1e-30",
             "HMM From": "1", "HMM To": "90", "Target From": "1", "Target To": "90",
             "Coverage": "0.9", "HMM File Name": "dbCAN-sub.hmm"},
        ])
        self._write_tsv(result_dir / "diamond.out", workflow.DIAMOND_HEADER, [
            {"Gene ID": "p1", "CAZy ID": "GH153+CE4", "% Identical": "50", "Length": "100",
             "Mismatches": "0", "Gap Open": "0", "Gene Start": "1", "Gene End": "100",
             "CAZy Start": "1", "CAZy End": "100", "E Value": "1e-30", "Bit Score": "100"},
        ])
        # Exercise reporting from a complete, structurally valid case.
        for name, header in workflow.REQUIRED_OUTPUT_HEADERS.items():
            if not (result_dir / name).exists():
                self._write_tsv(result_dir / name, header, [])
        for name in workflow.OUTPUT_FILES:
            if not (result_dir / name).exists():
                (result_dir / name).write_text("")
        (result_dir / "uniInput.faa").write_bytes((input_dir / "sample.faa").read_bytes())
        (result_dir / "cgc.gff").write_text(
            "ctg\t.\tCDS\t100\t399\t.\t+\t.\tprotein_id=p1;CGC_annotation=null\n"
            "ctg\t.\tCDS\t500\t679\t.\t-\t.\tprotein_id=p2;CGC_annotation=null\n")
        header, rows = self._read_tsv(result_dir / "overview.tsv")
        rows[0]["dbCAN_hmm"] = "CE4_e289(1-90)"
        rows[0]["dbCAN_sub"] = "GH153_e4(1-90)"
        rows[1]["dbCAN_hmm"] = "GH5_e1(1-60)"
        self._write_tsv(result_dir / "overview.tsv", header, rows)

        summary = workflow.summarize_results(input_dir / "sample.faa", input_dir / "sample.gff3",
                                             result_dir, output_dir)
        self.assertEqual(summary["unique_resolved_family_count"], 3)
        with (output_dir / "family_protein_counts.tsv").open(newline="") as handle:
            family_rows = {r["family"]: r for r in csv.DictReader(handle, delimiter="\t")}
        self.assertEqual(family_rows["CE4"]["unique_proteins_any_method"], "1")
        self.assertEqual(family_rows["GH153"]["unique_proteins_any_method"], "1")
        with (output_dir / "candidate_evidence.tsv").open(newline="") as handle:
            candidates = {r["protein_id"]: r for r in csv.DictReader(handle, delimiter="\t")}
        self.assertEqual(candidates["p1"]["resolved_family_agreement"], "CE4;GH153")
        self.assertEqual(candidates["p1"]["all_family_associations"], "CE4;GH153")

    def test_summary_rejects_metadata_nested_inside_results(self) -> None:
        results = self.root / "results"
        results.mkdir()
        with self.assertRaisesRegex(ValueError, "outside the native results"):
            workflow.summarize_results(self.root / "missing.faa", self.root / "missing.gff",
                                       results, results / "metadata")

    def test_database_manifest_comparison_ignores_only_generated_root_index(self) -> None:
        db_dir = self.root / "db"
        db_dir.mkdir()
        asset = db_dir / "profile.hmm"
        asset.write_bytes(b"immutable profile fixture\n")
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        (db_dir / "sha256sums.txt").write_text("generated index\n")
        expected = self.root / "expected.sha256"
        expected.write_text(f"{digest}  ./profile.hmm\n")
        observed = self.root / "observed.sha256"
        check = workflow.verify_database(db_dir, expected, observed)
        self.assertTrue(check["match"])
        self.assertEqual(check["expected_file_count"], 1)
        asset.write_bytes(b"changed profile fixture\n")
        self.assertFalse(workflow.verify_database(db_dir, expected)["match"])

    def test_static_zero_hit_fixture_is_structurally_valid_and_attested(self) -> None:
        fixture = Path(__file__).resolve().parent / "fixtures" / "zero_hit"
        observed = self.root / "diagnostics" / "observed_results.sha256"
        faa = fixture / "inputs" / "sample.faa"
        gff = fixture / "inputs" / "sample.gff3"
        result_dir = fixture / "results"
        status = json.loads((fixture / "metadata" / "stage_status.template.json").read_text())
        status.update({"run_id": "fixture-run",
            "input_faa_sha256": workflow.sha256_file(faa), "input_gff_sha256": workflow.sha256_file(gff),
            "results_dir": str(result_dir.resolve())})
        status["stages"]["substrate_prediction"]["output_sha256"] = workflow._hash_tree(result_dir)
        status_file = self.root / "fixture-status.json"
        status_file.write_text(json.dumps(status))
        result = workflow.validate_outputs(
            faa, gff, result_dir, status_file=status_file,
            require_stage_status=True, observed_manifest=observed)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["overview_candidates"], 0)
        self.assertEqual(result["cgc_count"], 0)
        self.assertTrue(observed.is_file())

    def _copy_zero_hit_case(self, label: str) -> tuple[Path, Path, Path]:
        fixture = Path(__file__).resolve().parent / "fixtures" / "zero_hit"
        sample_root = self.root / label
        shutil.copytree(fixture, sample_root)
        return (sample_root / "inputs/sample.faa", sample_root / "inputs/sample.gff3",
                sample_root / "results")

    def _validate_unattested(self, faa: Path, gff: Path, results: Path) -> dict:
        return workflow.validate_outputs(faa, gff, results, require_stage_status=False)

    def test_redirected_empty_results_rejects_stale_valid_archive(self) -> None:
        faa, gff, original_results = self._copy_zero_hit_case("redirect")
        new_results = self.root / "redirect" / "results_reproduced"
        new_results.mkdir()
        # The original path remains valid; validation must use only the selected path.
        self.assertEqual(self._validate_unattested(faa, gff, original_results)["overview_candidates"], 0)
        with self.assertRaisesRegex(FileNotFoundError, str(new_results)):
            self._validate_unattested(faa, gff, new_results)

    def test_duplicate_and_unknown_overview_ids_are_rejected(self) -> None:
        faa, gff, results = self._copy_zero_hit_case("ids")
        path = results / "overview.tsv"
        row = {name: "-" for name in workflow.OVERVIEW_HEADER}
        row.update({"Gene ID": "p1", "#ofTools": "0"})
        self._write_tsv(path, workflow.OVERVIEW_HEADER, [row, dict(row)])
        with self.assertRaisesRegex(ValueError, "duplicate protein IDs"):
            self._validate_unattested(faa, gff, results)

        row["Gene ID"] = "missing-protein"
        self._write_tsv(path, workflow.OVERVIEW_HEADER, [row])
        with self.assertRaisesRegex(ValueError, "unknown protein IDs"):
            self._validate_unattested(faa, gff, results)

    def test_processed_gff_coordinate_and_strand_discrepancies_are_rejected(self) -> None:
        faa, gff, results = self._copy_zero_hit_case("coordinates")
        path = results / "cgc.gff"
        original = path.read_text()
        changed = original.replace("CDS\t100\t399\t.\t+", "CDS\t101\t399\t.\t+")
        path.write_text(changed)
        with self.assertRaisesRegex(ValueError, "coordinate/strand changed"):
            self._validate_unattested(faa, gff, results)

        path.write_text(original.replace("CDS\t100\t399\t.\t+", "CDS\t100\t399\t.\t-"))
        with self.assertRaisesRegex(ValueError, "coordinate/strand changed"):
            self._validate_unattested(faa, gff, results)

    def test_overview_call_without_method_result_is_rejected(self) -> None:
        faa, gff, results = self._copy_zero_hit_case("overview-method")
        row = {name: "-" for name in workflow.OVERVIEW_HEADER}
        row.update({"Gene ID": "p1", "dbCAN_hmm": "GH5", "#ofTools": "1"})
        self._write_tsv(results / "overview.tsv", workflow.OVERVIEW_HEADER, [row])
        with self.assertRaisesRegex(ValueError, "corresponding result table has none"):
            self._validate_unattested(faa, gff, results)

    def test_every_threaded_stage_receives_requested_budget(self) -> None:
        commands = workflow.stage_commands(Path("env/bin/run_dbcan"), Path("sample.faa"), Path("sample.gff"),
            Path("results/sample"), Path("db"), 4, Path("results/sample/logs"))
        threaded = {name for name, argv, _ in commands if "--threads" in argv}
        self.assertEqual(threaded, {"CAZyme_annotation", "gff_process"})
        substrate = next(argv for name, argv, _ in commands if name == "substrate_prediction")
        self.assertTrue(substrate[1].endswith("run_dbcan_threadcap.py"))
        self.assertEqual(substrate[2:4], ["4", "substrate_prediction"])
        self.assertNotIn("--threads", substrate)

    def test_threadcap_sets_cpu_count_only_for_the_targeted_cli_process(self) -> None:
        before = {name: os.environ.get(name) for name in
            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}
        seen = []
        def entrypoint() -> None:
            seen.append((os.cpu_count(), list(sys.argv)))
        code = threadcap.main(["3", "substrate_prediction", "--mode=protein"], version="5.2.9",
                              entrypoint_loader=lambda: entrypoint)
        self.assertEqual(code, 0)
        self.assertEqual(seen[0][0], 3)
        self.assertEqual(seen[0][1][0], "run_dbcan")
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_failed_status_manifest_cannot_be_revalidated(self) -> None:
        status_file = self.root / "stage_status.json"
        status_file.write_text(json.dumps({"status": "failed", "stages": {}}))
        with self.assertRaisesRegex(ValueError, "marked 'failed'"):
            workflow._status_check(status_file, required=True)

    @staticmethod
    def _read_tsv(path: Path):
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            return reader.fieldnames, list(reader)

    @staticmethod
    def _write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
