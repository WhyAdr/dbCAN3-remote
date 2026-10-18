#!/usr/bin/env python3
"""Explicit-path dbCAN workflow helpers (Python standard library only).

This module validates paired Bakta FAA/GFF3 inputs, prepares run_dbcan's
top-level CDS GFF, verifies a pinned database snapshot, checks run outputs,
and writes overlap-aware summaries.  It intentionally never guesses paths
from its own location.
"""
from __future__ import annotations

from dbcan_outcomes import (Refusal, MissingPathRefusal, ExistingPathRefusal, RuntimeRefusal,
                            NegativeResult, MissingDataResult, StageFailure, structure_reader)

from dbcan_events import append_event, failure_context

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


VERSION = "0.3.1"
DBCAN_VERSION = "5.2.9"
SNAPSHOT = "db_v5-2-9_5-5-2026"
ARCHIVED_MANIFEST_SHA256 = "0f20c1986c32df59723cffc20b677789ed0c12819cd0939e16788f58dea406d2"
METHOD_COLUMNS = (("dbCAN_hmm", "dbCAN-HMM"), ("dbCAN_sub", "dbCAN-sub"), ("DIAMOND", "DIAMOND"))
FAMILY_RE = re.compile(r"(?<![A-Za-z0-9])((?:GH|GT|PL|CE|AA|CBM)\d+)", re.I)
UNRESOLVED_ROOTS = {"GH0", "GT0", "AA0", "PL0", "CE0", "CBM0"}
NON_HIT = {"", "-", "NA", "N/A", "nan", "None"}

OVERVIEW_HEADER = ["Gene ID", "EC#", "dbCAN_hmm", "dbCAN_sub", "DIAMOND", "#ofTools", "Recommend Results", "Substrate"]
HMM_HEADER = ["HMM Name", "HMM Length", "Target Name", "Target Length", "i-Evalue", "HMM From", "HMM To", "Target From", "Target To", "Coverage", "HMM File Name"]
SUBFAM_HEADER = ["Subfam Name", "Subfam Composition", "Subfam EC", "Substrate", "HMM Length", "Target Name", "Target Length", "i-Evalue", "HMM From", "HMM To", "Target From", "Target To", "Coverage", "HMM File Name"]
DIAMOND_HEADER = ["Gene ID", "CAZy ID", "% Identical", "Length", "Mismatches", "Gap Open", "Gene Start", "Gene End", "CAZy Start", "CAZy End", "E Value", "Bit Score"]
CGC_HEADER = ["CGC#", "Gene Type", "Contig ID", "Protein ID", "Gene Start", "Gene Stop", "Gene Strand", "Gene Annotation"]
CGC_SUMMARY_HEADER = ["CGC#", "Contig ID", "Cluster Start", "Cluster End", "Genes", "CAZymes", "TC", "TF", "STP", "Sulfatase", "Peptidase", "Signatures", "Length (bp)"]
SUBSTRATE_HEADER = ["#cgcid", "PULID", "dbCAN-PUL substrate", "bitscore", "signature pairs", "dbCAN-sub substrate", "dbCAN-sub substrate score"]

REQUIRED_OUTPUT_HEADERS = {
    "overview.tsv": OVERVIEW_HEADER,
    "dbCAN_hmm_results.tsv": HMM_HEADER,
    "dbCANsub_hmm_results.tsv": SUBFAM_HEADER,
    "diamond.out": DIAMOND_HEADER,
    "cgc_standard_out.tsv": CGC_HEADER,
    "cgc_standard_out_summary.tsv": CGC_SUMMARY_HEADER,
    "substrate_prediction.tsv": SUBSTRATE_HEADER,
    "total_cgc_info.tsv": ["Annotate Name", "Annotate Length", "Target Name", "Target Length", "i-Evalue", "Annotate From", "Annotate To", "Target From", "Target To", "Coverage", "Annotate File Name", "Type"],
    "STP_hmm_results.tsv": HMM_HEADER,
}
OUTPUT_FILES = [
    "uniInput.faa", "overview.tsv", "dbCAN_hmm_results.tsv", "dbCANsub_hmm_results.tsv",
    "diamond.out", "cgc.gff", "total_cgc_info.tsv", "cgc_standard_out.tsv",
    "cgc_standard_out_summary.tsv", "substrate_prediction.tsv", "PUL_blast.out",
    "STP_hmm_results.tsv", "diamond.out.tc", "diamond.out.tf",
    "diamond.out.peptidase", "diamond.out.sulfatase",
]
DB_ASSETS_BY_STAGE = {
    "CAZyme_annotation": ("CAZy.dmnd", "dbCAN.hmm", "dbCAN-sub.hmm", "fam-substrate-mapping.tsv"),
    "gff_process": ("TCDB.dmnd", "TF.hmm", "TF.dmnd", "STP.hmm", "peptidase_db.dmnd", "sulfatlas_db.dmnd"),
    "cgc_finder": (),
    "substrate_prediction": ("PUL.dmnd", "dbCAN-PUL.xlsx", "dbCAN-PUL"),
}
STAGE_NAMES = ("CAZyme_annotation", "gff_process", "cgc_finder", "substrate_prediction")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = str(path.parent / (path.name + '.' + uuid.uuid4().hex + '.tmp'))
    fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_tsv_atomic(path: Path, header: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header, delimiter="\t", extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


@structure_reader
def read_tsv(path: Path, expected_header: list[str] | None = None) -> list[dict[str, str]]:
    if not path.is_file():
        raise MissingPathRefusal('INPUT_MISSING', f"required result file is missing: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        header = reader.fieldnames or []
        if expected_header is not None and header != expected_header:
            raise NegativeResult('STRUCTURE_INVALID', f"unexpected TSV header in {path}: {header!r}; expected {expected_header!r}")
        if not header:
            raise NegativeResult('STRUCTURE_INVALID', f"TSV has no header: {path}")
        rows = list(reader)
    for n, row in enumerate(rows, 2):
        if None in row or any(v is None for v in row.values()):
            raise NegativeResult('STRUCTURE_INVALID', f"malformed TSV row {n} in {path}")
    return rows


def parse_attributes(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in text.split(";"):
        if not item:
            continue
        if "=" not in item:
            raise NegativeResult('STRUCTURE_INVALID', f"GFF3 attribute lacks '=': {item!r}")
        key, value = item.split("=", 1)
        key = unquote(key)
        if key in out:
            raise NegativeResult('STRUCTURE_INVALID', f"duplicate GFF3 attribute key {key!r}")
        out[key] = unquote(value)
    return out


@structure_reader
def parse_fasta(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise MissingPathRefusal('INPUT_MISSING', f"protein FASTA is missing: {path}")
    sequences: dict[str, str] = {}
    current: str | None = None
    chunks: list[str] = []

    def flush(line_no: int) -> None:
        nonlocal current, chunks
        if current is None:
            return
        seq = "".join(chunks).upper()
        if not seq:
            raise NegativeResult('STRUCTURE_INVALID', f"empty FASTA sequence for {current!r} in {path} near line {line_no}")
        if current in sequences:
            raise NegativeResult('STRUCTURE_INVALID', f"duplicate protein ID {current!r} in {path}")
        if re.search(r"[^A-Z*.-]", seq):
            raise NegativeResult('STRUCTURE_INVALID', f"invalid FASTA sequence symbols for {current!r} in {path}")
        sequences[current] = seq
        current, chunks = None, []

    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                flush(line_no)
                fields = line[1:].split()
                if not fields:
                    raise NegativeResult('STRUCTURE_INVALID', f"empty FASTA header at {path}:{line_no}")
                current = fields[0]
            elif line.strip():
                if current is None:
                    raise NegativeResult('STRUCTURE_INVALID', f"sequence before first FASTA header at {path}:{line_no}")
                chunks.append("".join(line.split()))
    flush(line_no + 1 if "line_no" in locals() else 1)
    if not sequences:
        raise NegativeResult('STRUCTURE_INVALID', f"no FASTA records in {path}")
    return sequences


@structure_reader
def parse_gff(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MissingPathRefusal('INPUT_MISSING', f"GFF3 is missing: {path}")
    seq_regions: dict[str, int] = {}
    circular: dict[str, bool] = {}
    organism = ""
    cds: dict[str, dict[str, Any]] = {}
    cds_order: list[str] = []
    raw_header: list[str] = []
    # Topology declarations may follow a CDS. Collect region topology first so
    # validity does not depend on feature order.
    with path.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            if raw.startswith("##FASTA"):
                break
            cols = raw.rstrip("\r\n").split("\t")
            if len(cols) == 9 and cols[2].lower() == "region":
                attrs = parse_attributes(cols[8])
                value = attrs.get("Is_circular", attrs.get("is_circular", "false")).lower() == "true"
                if cols[0] in circular and circular[cols[0]] != value:
                    raise NegativeResult('STRUCTURE_INVALID', f"conflicting topology declarations for {cols[0]}")
                circular[cols[0]] = value
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            if line.startswith("##FASTA"):
                break
            if line.startswith("# organism "):
                organism = line[len("# organism "):].strip()
            if line.startswith("##sequence-region "):
                cols = line.split()
                if len(cols) != 4:
                    raise NegativeResult('STRUCTURE_INVALID', f"malformed sequence-region directive at {path}:{line_no}")
                seqid, start, end = cols[1], int(cols[2]), int(cols[3])
                if start != 1 or end < 1:
                    raise NegativeResult('STRUCTURE_INVALID', f"invalid sequence-region bounds at {path}:{line_no}")
                if seqid in seq_regions and seq_regions[seqid] != end:
                    raise NegativeResult('STRUCTURE_INVALID', f"conflicting sequence-region length for {seqid!r}")
                seq_regions[seqid] = end
            if line.startswith("#"):
                raw_header.append(line)
                continue
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) != 9:
                raise NegativeResult('STRUCTURE_INVALID', f"expected 9 GFF3 columns at {path}:{line_no}, found {len(cols)}")
            seqid, source, feature, start_s, end_s, score, strand, phase, attr_text = cols
            attrs = parse_attributes(attr_text)
            if feature.lower() == "region":
                circular[seqid] = attrs.get("Is_circular", attrs.get("is_circular", "false")).lower() == "true"
            if feature != "CDS":
                continue
            pid = attrs.get("ID")
            if not pid:
                raise NegativeResult('STRUCTURE_INVALID', f"CDS without ID at {path}:{line_no}")
            if pid in cds:
                raise NegativeResult('STRUCTURE_INVALID', f"duplicate CDS ID {pid!r} in {path}")
            start, end = int(start_s), int(end_s)
            if start < 1 or end < start:
                raise NegativeResult('STRUCTURE_INVALID', f"invalid coordinates for {pid} at {path}:{line_no}")
            if strand not in {"+", "-", ".", "?"}:
                raise NegativeResult('STRUCTURE_INVALID', f"invalid strand {strand!r} for {pid} at {path}:{line_no}")
            if phase not in {"0", "1", "2"}:
                raise NegativeResult('STRUCTURE_INVALID', f"invalid CDS phase {phase!r} for {pid} at {path}:{line_no}")
            length = seq_regions.get(seqid)
            if length is not None and end > length:
                span = end - start + 1
                if not circular.get(seqid, False) or start > length or span > length or end > start + length - 1:
                    raise NegativeResult('STRUCTURE_INVALID', f"out-of-range CDS {pid} is not a valid single-wrap circular interval")
            cds[pid] = {
                "id": pid, "seqid": seqid, "start": start, "end": end, "strand": strand,
                "attributes": attrs, "phase": phase, "source": source, "feature": feature,
                "pseudogene": any(k.lower() in {"pseudo", "pseudogene"} for k in attrs),
                "line": line,
            }
            cds_order.append(pid)
    if not cds:
        raise NegativeResult('STRUCTURE_INVALID', f"no CDS features found in {path}")
    contigs = set(seq_regions) | set(circular) | {x["seqid"] for x in cds.values()}
    for seqid in contigs:
        circular.setdefault(seqid, False)
    return {"organism": organism, "seq_regions": seq_regions, "circular": circular,
            "cds": cds, "cds_order": cds_order, "header": raw_header}


def compare_faa_gff(faa: Path, gff: Path) -> dict[str, Any]:
    proteins = parse_fasta(faa)
    annotation = parse_gff(gff)
    cds = annotation["cds"]
    missing_from_faa = sorted(set(cds) - set(proteins))
    faa_only = sorted(set(proteins) - set(cds))
    if missing_from_faa or faa_only:
        raise Refusal('INPUT_MISMATCH', "FAA/GFF CDS IDs differ.", details={"cds_only_count": len(missing_from_faa), "faa_only_count": len(faa_only)})
    if len(proteins) != len(cds):
        raise Refusal('INPUT_MISMATCH', "FAA/GFF record counts differ despite matching ID sets")
    for pid, feature in cds.items():
        length = annotation["seq_regions"].get(feature["seqid"])
        if length is None:
            raise NegativeResult('STRUCTURE_INVALID', f"missing ##sequence-region length for contig {feature['seqid']!r}")
        end = feature["end"]
        if end > length:
            if not annotation["circular"].get(feature["seqid"], False):
                raise NegativeResult('STRUCTURE_INVALID', f"linear contig {feature['seqid']} has CDS {pid} ending beyond length {length}")
            span = end - feature["start"] + 1
            if span > length or end > feature["start"] + length - 1:
                raise NegativeResult('STRUCTURE_INVALID', f"CDS {pid} exceeds one circular contig traversal")
    return {"proteins": proteins, "annotation": annotation}


def prepare_local_gff(faa: Path, gff: Path, output: Path, report: Path) -> dict[str, Any]:
    _guard_output_files([output, report], [faa, gff])
    paired = compare_faa_gff(faa, gff)
    annotation = paired["annotation"]
    cds_ids = set(annotation["cds"])
    lines: list[str] = []
    with gff.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if line.startswith("##FASTA"):
                break
            if line.startswith("#"):
                lines.append(line)
                continue
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) == 9 and cols[2] == "CDS":
                attrs = parse_attributes(cols[8])
                if attrs.get("ID") not in cds_ids:
                    raise NegativeResult('STRUCTURE_INVALID', f"unexpected CDS while preparing local GFF: {attrs.get('ID')}")
                kept = [x for x in cols[8].split(";") if x and not x.startswith("Parent=")]
                cols[8] = ";".join(kept)
                lines.append("\t".join(cols))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp_name, output)
    finally:
        if os.path.exists(tmp_name): os.unlink(tmp_name)
    pseudo = sorted(pid for pid, row in annotation["cds"].items() if row["pseudogene"])
    wrapping = [{"protein_id": pid, "contig": row["seqid"], "start": row["start"], "end": row["end"],
                 "contig_length": annotation["seq_regions"][row["seqid"]]}
                for pid, row in annotation["cds"].items()
                if row["end"] > annotation["seq_regions"][row["seqid"]]]
    metadata = {"created_utc": utc_now(), "input_faa": str(faa.resolve()), "input_gff": str(gff.resolve()),
                "output_gff": str(output.resolve()), "gff_type": "prodigal",
                "adapter": "Bakta CDS rows are emitted as standalone features; only Parent attributes are removed",
                "protein_count": len(paired["proteins"]), "cds_count": len(annotation["cds"]),
                "exact_id_set_match": True, "faa_sha256": sha256_file(faa), "gff_sha256": sha256_file(gff),
                "local_gff_sha256": sha256_file(output), "organism": annotation["organism"],
                "pseudogene_cds_ids": pseudo, "origin_spanning_cds": wrapping,
                "contigs": [{"seqid": seqid, "length": annotation["seq_regions"].get(seqid),
                             "is_circular": annotation["circular"].get(seqid, False)}
                            for seqid in sorted(set(annotation["seq_regions"]) | set(annotation["circular"]))]}
    write_json_atomic(report, metadata)
    return metadata


def parse_sha256_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise MissingPathRefusal('INPUT_MISSING', 'The expected checksum manifest does not exist.', details={'path': str(path)})
    expected: dict[str, str] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            raise Refusal('MANIFEST_PATH_UNSAFE', f"malformed SHA256 manifest row at {path}:{line_no}")
        rel = parts[1].lstrip("* ")
        rel = rel.removeprefix("./").replace("\\", "/")
        if Path(rel).is_absolute() or ".." in Path(rel).parts or not rel:
            raise Refusal('MANIFEST_PATH_UNSAFE', "The checksum manifest contains an unsafe path.", details={"path": rel})
        if rel in expected:
            raise Refusal('MANIFEST_PATH_UNSAFE', f"duplicate path in checksum manifest: {rel}")
        expected[rel] = parts[0].lower()
    if not expected:
        raise Refusal('MANIFEST_PATH_UNSAFE', f"empty checksum manifest: {path}")
    return expected


def verify_database(db_dir: Path, expected_manifest: Path, observed_manifest: Path | None = None) -> dict[str, Any]:
    db_dir = db_dir.resolve()
    if not db_dir.is_dir():
        raise MissingPathRefusal('DB_UNVERIFIED', 'The selected database cache directory does not exist.', details={'db_dir': str(db_dir)})
    expected_manifest = expected_manifest.resolve()
    if db_dir == expected_manifest or db_dir in expected_manifest.parents:
        raise Refusal('PATHS_OVERLAP', "expected manifest must be outside the database directory")
    if observed_manifest is not None:
        observed_manifest = observed_manifest.resolve()
        if observed_manifest == expected_manifest or db_dir == observed_manifest or db_dir in observed_manifest.parents:
            raise Refusal('PATHS_OVERLAP', "observed manifest must be outside the database directory and must not overwrite the expected manifest")
    expected = parse_sha256_manifest(expected_manifest)
    observed: dict[str, str] = {}
    for path in sorted(db_dir.rglob("*")):
        # The dbCAN downloader's own checksum listing is a generated index,
        # not a database asset. The archived reference manifest excludes it.
        if path.is_file() and path.relative_to(db_dir).as_posix() != "sha256sums.txt":
            rel = path.relative_to(db_dir).as_posix()
            observed[rel] = sha256_file(path)
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    mismatches = sorted(k for k in set(expected) & set(observed) if expected[k] != observed[k])
    if observed_manifest is not None:
        observed_manifest.parent.mkdir(parents=True, exist_ok=True)
        with observed_manifest.open("w", encoding="utf-8", newline="\n") as f:
            for rel, digest in sorted(observed.items()):
                f.write(f"{digest}  ./{rel}\n")
    manifest_digest = sha256_file(expected_manifest)
    return {"snapshot": SNAPSHOT if manifest_digest == ARCHIVED_MANIFEST_SHA256 else "custom_manifest",
            "expected_manifest": str(expected_manifest.resolve()),
            "expected_manifest_sha256": sha256_file(expected_manifest), "expected_file_count": len(expected),
            "observed_file_count": len(observed), "missing": missing, "unexpected": unexpected,
            "mismatched": mismatches, "match": not (missing or unexpected or mismatches),
            "observed_manifest": str(observed_manifest.resolve()) if observed_manifest else None}


def db_preflight(db_dir: Path, expected_manifest: Path, required_stages: Iterable[str]) -> dict[str, Any]:
    checks = {}
    missing_by_stage = {}
    for stage in required_stages:
        missing = [name for name in DB_ASSETS_BY_STAGE[stage]
                   if not ((db_dir / name).is_dir() if name == "dbCAN-PUL" else (db_dir / name).is_file())]
        checks[stage] = {"required": list(DB_ASSETS_BY_STAGE[stage]), "missing": missing, "ready": not missing}
        if missing: missing_by_stage[stage] = missing
    if missing_by_stage:
        raise MissingPathRefusal('DB_UNVERIFIED', "Required database stage assets are missing.", details={"db_dir": str(db_dir), "missing_by_stage": missing_by_stage})
    manifest_check = verify_database(db_dir, expected_manifest)
    if not manifest_check["match"]:
        failure = Refusal('DB_UNVERIFIED', f"database directory does not match pinned {SNAPSHOT}: missing={len(manifest_check['missing'])}, unexpected={len(manifest_check['unexpected'])}, mismatched={len(manifest_check['mismatched'])}")
        failure.manifest_check = manifest_check
        raise failure
    return {"asset_checks": checks, "manifest_check": manifest_check}


def parse_family_roots(value: str) -> set[str]:
    roots = {m.group(1).upper() for m in FAMILY_RE.finditer(value or "")}
    return roots - UNRESOLVED_ROOTS


def hit(value: str | None) -> bool:
    return bool((value or "").strip() not in NON_HIT)


def _positive_method_count(row: dict[str, str]) -> int:
    return sum(hit(row.get(col, "")) for col, _ in METHOD_COLUMNS)


def _as_int(value: str, label: str, path: Path) -> int:
    try:
        parsed = Decimal(value)
        if not parsed.is_finite() or parsed != parsed.to_integral_value():
            raise NegativeResult('STRUCTURE_INVALID', "value is not a finite integer")
        return int(parsed)
    except Exception as exc:
        raise NegativeResult('STRUCTURE_INVALID', f"invalid integer {label}={value!r} in {path}") from exc


def _as_number(value: str, label: str, path: Path, *, minimum: float = 0,
               maximum: float | None = None) -> float:
    try:
        number = float(value)
        if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
            raise NegativeResult('STRUCTURE_INVALID', "number is outside the permitted finite range")
        return number
    except (TypeError, ValueError, OverflowError) as exc:
        raise NegativeResult('STRUCTURE_INVALID', f"invalid numeric {label}={value!r} in {path}") from exc


def _check_domain_rows(path: Path, rows: list[dict[str, str]], proteins: dict[str, str], *, subfam: bool = False) -> None:
    for n, row in enumerate(rows, 2):
        pid = row["Target Name"]
        if pid not in proteins:
            raise NegativeResult('STRUCTURE_INVALID', f"unknown protein {pid!r} at {path}:{n}")
        actual_len = len(proteins[pid].rstrip("*"))
        tlen = _as_int(row["Target Length"], "Target Length", path)
        if tlen != actual_len:
            raise NegativeResult('STRUCTURE_INVALID', f"Target Length {tlen} differs from FASTA length {actual_len} for {pid} in {path}:{n}")
        qstart = _as_int(row["Target From"], "Target From", path)
        qend = _as_int(row["Target To"], "Target To", path)
        hstart = _as_int(row["HMM From"], "HMM From", path)
        hend = _as_int(row["HMM To"], "HMM To", path)
        hlen = _as_int(row["HMM Length"], "HMM Length", path)
        if qstart < 1 or qend < qstart or qend > actual_len:
            raise NegativeResult('STRUCTURE_INVALID', f"invalid query domain bounds {qstart}-{qend}/{actual_len} for {pid} in {path}:{n}")
        if hstart < 1 or hend < hstart or hend > hlen:
            raise NegativeResult('STRUCTURE_INVALID', f"invalid HMM bounds {hstart}-{hend}/{hlen} for {pid} in {path}:{n}")
        _as_number(row["i-Evalue"], "i-Evalue", path)
        _as_number(row["Coverage"], "Coverage", path, maximum=1)
        if subfam and not row["Subfam Name"].strip():
            raise NegativeResult('STRUCTURE_INVALID', f"empty subfamily name in {path}:{n}")


def _diamond_overview_label(label: str) -> str:
    """Reproduce 5.2.9 OverviewGenerator.extract_cazy_id without pandas."""
    parts = [p.strip() for p in label.split("|")]
    truncated = False
    if any("fasta" in p.lower() for p in parts):
        for i, part in enumerate(parts):
            if part.isdigit():
                parts, truncated = parts[:i], True
                break
    matches = [p for p in parts if re.match(r"^(GH|GT|CBM|AA|CE|PL)", p)]
    return "+".join(matches) if matches else (parts[0] if truncated and parts else label)


def _expected_method_calls(tables: dict[str, list[dict[str, str]]]) -> dict[str, dict[str, Counter]]:
    calls: dict[str, dict[str, Counter]] = {key: defaultdict(Counter) for key, _ in METHOD_COLUMNS}
    for filename, key, name in (("dbCAN_hmm_results.tsv", "dbCAN_hmm", "HMM Name"),
                                ("dbCANsub_hmm_results.tsv", "dbCAN_sub", "Subfam Name")):
        for row in tables[filename]:
            label = row[name].split(".hmm")[0]
            start = _as_int(row["Target From"], "Target From", Path(filename))
            end = _as_int(row["Target To"], "Target To", Path(filename))
            calls[key][row["Target Name"]][f"{label}({start}-{end})"] += 1
    for row in tables["diamond.out"]:
        calls["DIAMOND"][row["Gene ID"]].update(_diamond_overview_label(row["CAZy ID"]).split("+"))
    return calls


def _check_accessory_tables(results_dir: Path, tables: dict[str, list[dict[str, str]]],
                            proteins: dict[str, str]) -> None:
    _check_domain_rows(results_dir / "STP_hmm_results.tsv", tables["STP_hmm_results.tsv"], proteins)
    known_types = {"TC", "TF", "STP", "Sulfatase", "Peptidase"}
    for n, row in enumerate(tables["total_cgc_info.tsv"], 2):
        path = results_dir / "total_cgc_info.tsv"
        pid = row["Target Name"]
        if pid not in proteins:
            raise NegativeResult('STRUCTURE_INVALID', f"unknown accessory protein {pid!r} in {path}:{n}")
        length = len(proteins[pid].rstrip("*"))
        if _as_int(row["Target Length"], "Target Length", path) != length:
            raise NegativeResult('STRUCTURE_INVALID', f"accessory target length differs for {pid}")
        start = _as_int(row["Target From"], "Target From", path)
        end = _as_int(row["Target To"], "Target To", path)
        model_length = _as_int(row["Annotate Length"], "Annotate Length", path)
        model_start = _as_int(row["Annotate From"], "Annotate From", path)
        model_end = _as_int(row["Annotate To"], "Annotate To", path)
        if not 1 <= start <= end <= length or not 1 <= model_start <= model_end <= model_length:
            raise NegativeResult('STRUCTURE_INVALID', f"invalid accessory domain bounds for {pid} in {path}:{n}")
        if row["Type"] not in known_types:
            raise NegativeResult('STRUCTURE_INVALID', f"unknown accessory category {row['Type']!r} in {path}:{n}")
        _as_number(row["i-Evalue"], "i-Evalue", path)
        _as_number(row["Coverage"], "Coverage", path, maximum=1 if row["Type"] == "STP" else 100)
    for filename, prefix in (("diamond.out.tc", "TCDB"), ("diamond.out.tf", "TF"),
                              ("diamond.out.peptidase", "Peptidase"), ("diamond.out.sulfatase", "Sul")):
        path = results_dir / filename
        expected_header = [f"{prefix} ID", f"{prefix} Length", "Target ID", "Target Length", "EVALUE",
                           f"{prefix} START", f"{prefix} END", "QSTART", "QEND", "COVERAGE", "Database"]
        rows = read_tsv(path, expected_header) if path.stat().st_size else []
        # The recorded outputs use positional DIAMOND-to-signature headers.
        # Require the target and numeric fields independently of reference-name capitalization.
        for n, row in enumerate(rows, 2):
            required = {"Target ID", "Target Length", "EVALUE", "QSTART", "QEND", "COVERAGE"}
            if not required <= row.keys():
                raise NegativeResult('STRUCTURE_INVALID', f"unexpected accessory header in {path}")
            pid = row["Target ID"]
            if pid not in proteins:
                raise NegativeResult('STRUCTURE_INVALID', f"unknown accessory protein {pid!r} in {path}:{n}")
            length = len(proteins[pid].rstrip("*"))
            if _as_int(row["Target Length"], "Target Length", path) != length:
                raise NegativeResult('STRUCTURE_INVALID', f"accessory target length differs for {pid} in {path}")
            start = _as_int(row["QSTART"], "QSTART", path)
            end = _as_int(row["QEND"], "QEND", path)
            if not 1 <= start <= end <= length:
                raise NegativeResult('STRUCTURE_INVALID', f"invalid accessory query bounds for {pid} in {path}:{n}")
            ref_length = _as_int(row[f"{prefix} Length"], f"{prefix} Length", path)
            ref_start = _as_int(row[f"{prefix} START"], f"{prefix} START", path)
            ref_end = _as_int(row[f"{prefix} END"], f"{prefix} END", path)
            if not 1 <= ref_start <= ref_end <= ref_length:
                raise NegativeResult('STRUCTURE_INVALID', f"invalid accessory reference bounds for {pid} in {path}:{n}")
            _as_number(row["EVALUE"], "EVALUE", path)
            _as_number(row["COVERAGE"], "COVERAGE", path, maximum=100)


def normalize_status_vocab(data):
    """Read either legacy records or v2; reject contradictory or unknown tokens."""
    if not isinstance(data, dict) or type(data.get('schema_version', 1)) is not int or data.get('schema_version', 1) not in {1, 2}:
        raise ValueError('unsupported stage-status schema')
    run_map = {'complete': 'succeeded', 'stages_complete': 'stages_succeeded'}
    stage_map = {'completed': 'succeeded'}
    state = data.get('run', {}).get('state', data.get('status', 'incomplete'))
    state = run_map.get(state, state)
    if state not in {'pending', 'running', 'stages_succeeded', 'succeeded', 'failed', 'incomplete'}:
        raise ValueError('unknown run state')
    if 'status' in data and run_map.get(data['status'], data['status']) != state:
        raise ValueError('contradictory run state')
    normalized = {'run': {'state': state}, 'stages': {}}
    if not isinstance(data.get('stages', {}), dict): raise ValueError('stages must be an object')
    for name, record in data.get('stages', {}).items():
        token = record.get('state', record.get('status', 'pending'))
        token = stage_map.get(token, token)
        if token not in {'pending', 'running', 'succeeded', 'failed', 'skipped'}:
            raise ValueError('unknown stage state')
        if 'status' in record and stage_map.get(record['status'], record['status']) != token:
            raise ValueError('contradictory stage state')
        normalized['stages'][name] = {**record, 'state': token}
    return normalized


def _v2_status_document(data):
    normalized = normalize_status_vocab(data)
    result = {**data, 'schema_version': 2, 'run': normalized['run'], 'status': normalized['run']['state']}
    if 'stages' in data:
        result['stages'] = {key: {**value, 'status': value['state']} for key, value in normalized['stages'].items()}
    return result


def _status_check(status_file: Path | None, required: bool, *, faa: Path | None = None,
                  gff: Path | None = None, results_dir: Path | None = None) -> dict[str, Any]:
    if status_file is None:
        if required:
            raise Refusal('ATTESTATION_REQUIRED', "Stage completion evidence is missing; pass --status-file or use --allow-unattested for structural review only.")
        return {"present": False, "attested": False, "overall": "structurally_valid_execution_unattested"}
    if not status_file.is_file():
        raise Refusal('ATTESTATION_REJECTED', "The supplied --status-file does not exist.", details={'status_file': str(status_file)})
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
        normalized = normalize_status_vocab(data)
    except (ValueError, TypeError, AttributeError, KeyError, OSError) as exc:
        raise Refusal('ATTESTATION_REJECTED', "The supplied stage status manifest is malformed.", details={'status_file': str(status_file)}) from exc
    state = normalized['run']['state']
    if state not in {'stages_succeeded', 'succeeded'}:
        raise Refusal('ATTESTATION_REJECTED', f"stage status manifest is marked '{state}': {status_file}")
    if data:
        if not isinstance(data.get("run_id"), str) or not data["run_id"]:
            raise Refusal('ATTESTATION_REJECTED', f"stage status manifest lacks a run ID: {status_file}")
        for label, input_path, key in (("FAA", faa, "input_faa_sha256"), ("GFF", gff, "input_gff_sha256")):
            if input_path is None or not data.get(key):
                raise Refusal('ATTESTATION_REJECTED', f"stage status manifest lacks {label} identity evidence: {status_file}")
            if data[key] != sha256_file(input_path):
                raise Refusal('ATTESTATION_REJECTED', f"stage status manifest {label} hash does not match the selected input: {status_file}")
        if results_dir is None or not isinstance(data.get("results_dir"), str) or Path(data["results_dir"]).resolve() != results_dir.resolve():
            raise Refusal('ATTESTATION_REJECTED', f"stage status manifest results path does not match the selected results directory: {status_file}")
    stages = data.get("stages", {})
    problems = []
    for stage in STAGE_NAMES:
        record = stages.get(stage)
        if not record or normalized["stages"].get(stage, {}).get("state") != "succeeded" or type(record.get("exit_code")) is not int or record.get("exit_code") != 0:
            problems.append(stage)
    if problems:
        raise Refusal('ATTESTATION_REJECTED', "One or more required stages are incomplete or unsuccessful.", details={"stages": problems})
    if results_dir is not None:
        expected_outputs = stages[STAGE_NAMES[-1]].get("output_sha256")
        if not expected_outputs:
            raise Refusal('ATTESTATION_REJECTED', "stage status manifest lacks final output hash evidence")
        if expected_outputs != _hash_tree(results_dir):
            raise Refusal('ATTESTATION_REJECTED', "stage status manifest output hashes differ from the selected results")
    return {"present": True, "attested": True, "overall": "complete", "status_file": str(status_file.resolve()),
            "run_id": data.get("run_id"), "source": data.get("source", "workflow stage manifest")}


def validate_outputs(faa: Path, gff: Path, results_dir: Path, *, status_file: Path | None = None,
                     require_stage_status: bool = True, observed_manifest: Path | None = None) -> dict[str, Any]:
    """Cross-check one explicitly selected results directory against its inputs."""
    if not results_dir.is_dir():
        raise MissingPathRefusal('RESULTS_DIR_MISSING', f"results directory does not exist: {results_dir}")
    paired = compare_faa_gff(faa, gff)
    proteins = paired["proteins"]
    annotation = paired["annotation"]
    missing = [name for name in OUTPUT_FILES if not (results_dir / name).is_file()]
    if missing:
        raise MissingDataResult('STRUCTURE_INVALID', f"missing required outputs in {results_dir}: {missing}")
    tables = {name: read_tsv(results_dir / name, header) for name, header in REQUIRED_OUTPUT_HEADERS.items()}
    overview = tables["overview.tsv"]
    overview_ids = [r["Gene ID"].strip() for r in overview]
    if any(not pid for pid in overview_ids):
        raise NegativeResult('STRUCTURE_INVALID', "overview.tsv contains an empty Gene ID")
    if len(overview_ids) != len(set(overview_ids)):
        raise NegativeResult('STRUCTURE_INVALID', "overview.tsv contains duplicate protein IDs")
    unknown_overview = sorted(set(overview_ids) - set(proteins))
    if unknown_overview:
        raise NegativeResult('STRUCTURE_INVALID', f"overview.tsv contains unknown protein IDs: {unknown_overview[:10]}")

    method_hits: dict[str, set[str]] = {key: set() for key, _ in METHOD_COLUMNS}
    for fname, key in (("dbCAN_hmm_results.tsv", "dbCAN_hmm"), ("dbCANsub_hmm_results.tsv", "dbCAN_sub")):
        rows = tables[fname]
        _check_domain_rows(results_dir / fname, rows, proteins, subfam=(key == "dbCAN_sub"))
        method_hits[key] = {r["Target Name"] for r in rows}
    drows = tables["diamond.out"]
    for n, row in enumerate(drows, 2):
        pid = row["Gene ID"]
        if pid not in proteins:
            raise NegativeResult('STRUCTURE_INVALID', f"unknown DIAMOND protein ID {pid!r} in diamond.out:{n}")
        qstart = _as_int(row["Gene Start"], "Gene Start", results_dir / "diamond.out")
        qend = _as_int(row["Gene End"], "Gene End", results_dir / "diamond.out")
        if qstart < 1 or qend < qstart or qend > len(proteins[pid].rstrip("*")):
            raise NegativeResult('STRUCTURE_INVALID', f"invalid DIAMOND query bounds for {pid} at diamond.out:{n}")
        _as_number(row["% Identical"], "% Identical", results_dir / "diamond.out", maximum=100)
        _as_number(row["E Value"], "E Value", results_dir / "diamond.out")
        _as_number(row["Bit Score"], "Bit Score", results_dir / "diamond.out")
        for field in ("Length", "Mismatches", "Gap Open", "CAZy Start", "CAZy End"):
            number = _as_int(row[field], field, results_dir / "diamond.out")
            if number < (0 if field in {"Mismatches", "Gap Open"} else 1):
                raise NegativeResult('STRUCTURE_INVALID', f"invalid DIAMOND {field} for {pid}")
    method_hits["DIAMOND"] = {r["Gene ID"] for r in drows}
    _check_accessory_tables(results_dir, tables, proteins)
    expected_calls = _expected_method_calls(tables)

    row_by_id = {r["Gene ID"]: r for r in overview}
    for pid, row in row_by_id.items():
        actual = _positive_method_count(row)
        reported = _as_int(row["#ofTools"], "#ofTools", results_dir / "overview.tsv")
        if reported != actual:
            raise NegativeResult('STRUCTURE_INVALID', f"#ofTools={reported} but {actual} method columns are positive for {pid}")
        for col, _ in METHOD_COLUMNS:
            if hit(row.get(col, "")) and pid not in method_hits[col]:
                raise NegativeResult('STRUCTURE_INVALID', f"overview says {pid} has a {col} hit but the corresponding result table has none")
            if not hit(row.get(col, "")) and pid in method_hits[col]:
                raise NegativeResult('STRUCTURE_INVALID', f"{col} result table contains {pid}, but overview has no {col} call")
            if hit(row.get(col, "")) and Counter(row[col].split("+")) != expected_calls[col][pid]:
                raise NegativeResult('STRUCTURE_INVALID', f"overview {col} label/domain evidence differs from raw results for {pid}")
    union_hits = set().union(*method_hits.values())
    if set(overview_ids) != union_hits:
        extra = sorted(set(overview_ids) - union_hits)
        absent = sorted(union_hits - set(overview_ids))
        raise NegativeResult('STRUCTURE_INVALID', f"overview IDs disagree with method tables; overview_only={extra[:10]}, method_only={absent[:10]}")

    processed_faa = parse_fasta(results_dir / "uniInput.faa")
    if set(processed_faa) != set(proteins):
        raise NegativeResult('STRUCTURE_INVALID', f"uniInput.faa ID set differs from source FAA; missing={sorted(set(proteins)-set(processed_faa))[:10]}, extra={sorted(set(processed_faa)-set(proteins))[:10]}")
    for pid, seq in proteins.items():
        if seq != processed_faa[pid]:
            raise NegativeResult('STRUCTURE_INVALID', f"sequence changed between input FAA and uniInput.faa for {pid}")

    expected_cds = annotation["cds"]
    cgc_gff_rows: dict[str, dict[str, Any]] = {}
    with (results_dir / "cgc.gff").open("r", encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 9:
                raise NegativeResult('STRUCTURE_INVALID', f"cgc.gff row does not have 9 columns at line {n}")
            if cols[2] != "CDS":
                continue
            attrs = parse_attributes(cols[8])
            pid = attrs.get("protein_id") or attrs.get("ID")
            if not pid:
                raise NegativeResult('STRUCTURE_INVALID', f"cgc.gff CDS lacks protein_id/ID at line {n}")
            if pid in cgc_gff_rows:
                raise NegativeResult('STRUCTURE_INVALID', f"duplicate processed GFF protein ID {pid}")
            if pid not in expected_cds:
                raise NegativeResult('STRUCTURE_INVALID', f"unknown processed GFF protein ID {pid}")
            source = expected_cds[pid]
            observed_tuple = (cols[0], int(cols[3]), int(cols[4]), cols[6])
            expected_tuple = (source["seqid"], source["start"], source["end"], source["strand"])
            if observed_tuple != expected_tuple:
                raise NegativeResult('STRUCTURE_INVALID', f"contig/coordinate/strand changed for {pid}: {observed_tuple} != {expected_tuple}")
            cgc_gff_rows[pid] = {"contig": cols[0], "start": int(cols[3]), "end": int(cols[4]),
                                 "strand": cols[6], "annotation": attrs.get("CGC_annotation", "null")}
    if set(cgc_gff_rows) != set(expected_cds):
        raise NegativeResult('STRUCTURE_INVALID', f"cgc.gff CDS IDs differ from source GFF; missing={sorted(set(expected_cds)-set(cgc_gff_rows))[:10]}, extra={sorted(set(cgc_gff_rows)-set(expected_cds))[:10]}")

    cgc_rows = tables["cgc_standard_out.tsv"]
    summary_rows = tables["cgc_standard_out_summary.tsv"]
    by_cluster: dict[str, list[dict[str, str]]] = defaultdict(list)
    member_seen: set[tuple[str, str]] = set()
    for n, row in enumerate(cgc_rows, 2):
        cid, pid = row["CGC#"], row["Protein ID"]
        if not cid or not pid:
            raise NegativeResult('STRUCTURE_INVALID', f"empty CGC# or Protein ID at cgc_standard_out.tsv:{n}")
        key = (cid, pid)
        if key in member_seen:
            raise NegativeResult('STRUCTURE_INVALID', f"duplicate CGC member {pid} in {cid}")
        member_seen.add(key)
        if pid not in expected_cds:
            raise NegativeResult('STRUCTURE_INVALID', f"unknown CGC member protein ID {pid}")
        src = expected_cds[pid]
        tup = (row["Contig ID"], _as_int(row["Gene Start"], "Gene Start", results_dir / "cgc_standard_out.tsv"),
               _as_int(row["Gene Stop"], "Gene Stop", results_dir / "cgc_standard_out.tsv"), row["Gene Strand"])
        expected_tuple = (src["seqid"], src["start"], src["end"], src["strand"])
        if tup != expected_tuple:
            raise NegativeResult('STRUCTURE_INVALID', f"CGC membership coordinates differ from source for {pid}: {tup} != {expected_tuple}")
        if row["Gene Annotation"] != cgc_gff_rows[pid]["annotation"]:
            raise NegativeResult('STRUCTURE_INVALID', f"CGC annotation differs between cgc.gff and membership table for {pid}")
        allowed_types = {"CAZyme", "TC", "TF", "STP", "Sulfatase", "Peptidase", "null"}
        tokens = {part.split("|", 1)[0] for part in row["Gene Annotation"].split("+")}
        if row["Gene Type"] not in allowed_types or row["Gene Type"] not in tokens:
            raise NegativeResult('STRUCTURE_INVALID', f"CGC gene type differs from annotation categories for {pid}")
        by_cluster[cid].append(row)
    summary_by_id: dict[str, dict[str, str]] = {}
    for row in summary_rows:
        cid = row["CGC#"]
        if not cid or cid in summary_by_id:
            raise NegativeResult('STRUCTURE_INVALID', f"empty or duplicate CGC ID in summary: {cid!r}")
        summary_by_id[cid] = row
    if set(summary_by_id) != set(by_cluster):
        raise NegativeResult('STRUCTURE_INVALID', f"CGC IDs differ between member table and summary; member_only={sorted(set(by_cluster)-set(summary_by_id))}, summary_only={sorted(set(summary_by_id)-set(by_cluster))}")
    type_columns = {"CAZyme": "CAZymes", "TC": "TC", "TF": "TF", "STP": "STP", "Sulfatase": "Sulfatase", "Peptidase": "Peptidase"}
    for cid, members in by_cluster.items():
        summary = summary_by_id[cid]
        contigs = {r["Contig ID"] for r in members}
        if len(contigs) != 1 or summary["Contig ID"] not in contigs:
            raise NegativeResult('STRUCTURE_INVALID', f"inconsistent contig membership for {cid}")
        starts = [_as_int(r["Gene Start"], "Gene Start", results_dir / "cgc_standard_out.tsv") for r in members]
        ends = [_as_int(r["Gene Stop"], "Gene Stop", results_dir / "cgc_standard_out.tsv") for r in members]
        values = {"Genes": len(members), "Cluster Start": min(starts), "Cluster End": max(ends),
                  "Length (bp)": max(ends) - min(starts) + 1,
                  "Signatures": sum(r["Gene Type"] != "null" for r in members)}
        for gene_type, col in type_columns.items():
            values[col] = sum(r["Gene Type"] == gene_type for r in members)
        for key, expected in values.items():
            observed = _as_int(summary[key], key, results_dir / "cgc_standard_out_summary.tsv")
            if observed != expected:
                raise NegativeResult('STRUCTURE_INVALID', f"{cid} summary {key}={observed}, member rows imply {expected}")

    substrate_rows = tables["substrate_prediction.tsv"]
    known_cgc_keys = {f"{summary['Contig ID']}|{cid}" for cid, summary in summary_by_id.items()}
    seen_substrates = set()
    for row in substrate_rows:
        cgcid = row["#cgcid"]
        if cgcid not in known_cgc_keys:
            raise NegativeResult('STRUCTURE_INVALID', f"substrate row references unknown CGC {cgcid!r}")
        if cgcid in seen_substrates:
            raise NegativeResult('STRUCTURE_INVALID', f"duplicate substrate row for {cgcid}")
        seen_substrates.add(cgcid)

    status = _status_check(status_file, require_stage_status, faa=faa, gff=gff, results_dir=results_dir)
    methods_per_protein = Counter(str(_positive_method_count(r)) for r in overview)
    family_agreement = set()
    for row in overview:
        roots_by_method = [parse_family_roots(row.get(col, "")) for col, _ in METHOD_COLUMNS]
        roots = set().union(*roots_by_method)
        if any(sum(root in values for values in roots_by_method) >= 2 for root in roots):
            family_agreement.add(row["Gene ID"])
    result = {"schema_version": 2, "evidence": {"structure": "valid", "attestation": "attested" if status["attested"] else "unattested"},
              "run_id": status.get("run_id"), "sample": faa.stem, "status": status["overall"], "execution_attested": status["attested"],
              "faa_proteins": len(proteins), "gff_cds": len(expected_cds), "overview_candidates": len(overview),
              "method_hit_proteins": {name: len(method_hits[key]) for key, name in METHOD_COLUMNS},
              "method_count_distribution": dict(sorted(methods_per_protein.items())),
              "positive_in_two_or_more_methods": sum(_positive_method_count(r) >= 2 for r in overview),
              "resolved_family_agreement": len(family_agreement), "cgc_count": len(summary_rows),
              "cgc_member_rows": len(cgc_rows), "substrate_rows": len(substrate_rows),
              "pseudogene_cds_count": sum(x["pseudogene"] for x in expected_cds.values()),
              "circular_contigs": sum(annotation["circular"].values()),
              "origin_spanning_cds": [{"id": pid, "contig": row["seqid"], "start": row["start"], "end": row["end"],
                                       "contig_length": annotation["seq_regions"][row["seqid"]]}
                                      for pid, row in expected_cds.items()
                                      if row["end"] > annotation["seq_regions"][row["seqid"]]],
              "results_dir": str(results_dir.resolve()), "input_faa_sha256": sha256_file(faa),
              "input_gff_sha256": sha256_file(gff)}
    if observed_manifest is not None:
        observed_manifest = observed_manifest.resolve()
        for protected in (results_dir.resolve(), faa.resolve().parent, gff.resolve().parent):
            if observed_manifest == protected or protected in observed_manifest.parents:
                raise Refusal('PATHS_OVERLAP', "observed result manifest must be outside native results and input directories")
        if status_file is not None and observed_manifest == status_file.resolve():
            raise Refusal('PATHS_OVERLAP', "observed result manifest must not overwrite stage status")
        observed_manifest.parent.mkdir(parents=True, exist_ok=True)
        files = [p for p in sorted(results_dir.rglob("*")) if p.is_file()]
        with observed_manifest.open("w", encoding="utf-8", newline="\n") as f:
            for path in files:
                f.write(f"{sha256_file(path)}  ./{path.relative_to(results_dir).as_posix()}\n")
    return result


def summarize_results(faa: Path, gff: Path, results_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Write complete multi-assignment evidence tables from native dbCAN files."""
    results_dir = results_dir.resolve()
    output_dir = output_dir.resolve()
    if results_dir == output_dir or results_dir in output_dir.parents or output_dir in results_dir.parents:
        raise Refusal('PATHS_OVERLAP', "summary output directory must be separate from and outside the native results directory")
    for input_root in {faa.resolve().parent, gff.resolve().parent}:
        if output_dir == input_root or output_dir in input_root.parents or input_root in output_dir.parents:
            raise Refusal('PATHS_OVERLAP', "summary metadata must be separate from the input directory")
    validate_outputs(faa, gff, results_dir, require_stage_status=False)
    paired = compare_faa_gff(faa, gff)
    proteins = paired["proteins"]
    annotation = paired["annotation"]
    overview = read_tsv(results_dir / "overview.tsv", OVERVIEW_HEADER)
    hhm_rows = read_tsv(results_dir / "dbCAN_hmm_results.tsv", HMM_HEADER)
    sub_rows = read_tsv(results_dir / "dbCANsub_hmm_results.tsv", SUBFAM_HEADER)
    diamond_rows = read_tsv(results_dir / "diamond.out", DIAMOND_HEADER)
    pseudo = {pid for pid, r in annotation["cds"].items() if r["pseudogene"]}

    associations: dict[tuple[str, str, str], dict[str, Any]] = {}
    def add_association(pid: str, method: str, raw_label: str, evidence: str, source_file: str, boundary: str = "") -> None:
        roots = parse_family_roots(raw_label)
        # Keep unresolved labels auditable, but exclude them from resolved-family counts.
        unresolved = sorted({m.group(1).upper() for m in FAMILY_RE.finditer(raw_label or "")} & UNRESOLVED_ROOTS)
        family_values = roots | set(unresolved)
        for family in family_values:
            key = (pid, method, family)
            item = associations.setdefault(key, {"protein_id": pid, "method": method, "family": family,
                "family_class": re.match(r"[A-Z]+", family).group(0) if re.match(r"[A-Z]+", family) else "",
                "evidence_type": evidence, "source_file": source_file, "raw_labels": set(), "domain_boundaries_aa": set(),
                "resolved_family": family not in UNRESOLVED_ROOTS, "pseudogene_marked": pid in pseudo})
            item["raw_labels"].add(raw_label)
            if boundary:
                item["domain_boundaries_aa"].add(boundary)

    domain_instances: list[dict[str, Any]] = []
    for row in hhm_rows:
        pid = row["Target Name"]
        root = next(iter(parse_family_roots(row["HMM Name"])), "")
        bounds = f"{row['Target From']}-{row['Target To']}"
        if root:
            add_association(pid, "dbCAN-HMM", row["HMM Name"], "query-aligned HMM domain", "dbCAN_hmm_results.tsv", bounds)
        domain_instances.append({"protein_id": pid, "method": "dbCAN-HMM", "model": row["HMM Name"],
            "family": root, "target_start_aa": row["Target From"], "target_end_aa": row["Target To"],
            "target_length_aa": row["Target Length"], "hmm_start": row["HMM From"], "hmm_end": row["HMM To"],
            "i_evalue": row["i-Evalue"], "coverage": row["Coverage"], "support_type": "query-aligned domain"})
    for row in sub_rows:
        pid = row["Target Name"]
        root = next(iter(parse_family_roots(row["Subfam Name"])), "")
        bounds = f"{row['Target From']}-{row['Target To']}"
        if root:
            add_association(pid, "dbCAN-sub", row["Subfam Name"], "query-aligned subfamily domain", "dbCANsub_hmm_results.tsv", bounds)
        domain_instances.append({"protein_id": pid, "method": "dbCAN-sub", "model": row["Subfam Name"],
            "family": root, "target_start_aa": row["Target From"], "target_end_aa": row["Target To"],
            "target_length_aa": row["Target Length"], "hmm_start": row["HMM From"], "hmm_end": row["HMM To"],
            "i_evalue": row["i-Evalue"], "coverage": row["Coverage"], "support_type": "query-aligned subfamily domain"})
    diamond_labels: dict[str, set[str]] = defaultdict(set)
    for row in diamond_rows:
        pid, label = row["Gene ID"], row["CAZy ID"]
        diamond_labels[pid].add(label)
        add_association(pid, "DIAMOND", label,
                        "reference-protein family association; query domain not established by this hit alone", "diamond.out")
    association_rows = []
    for item in associations.values():
        association_rows.append({**item, "raw_labels": ";".join(sorted(item["raw_labels"])),
                                 "domain_boundaries_aa": ";".join(sorted(item["domain_boundaries_aa"]))})
    association_rows.sort(key=lambda r:(r["protein_id"],r["family"],r["method"]))
    write_tsv_atomic(output_dir / "protein_family_associations.tsv",
        ["protein_id","method","family","family_class","evidence_type","source_file","raw_labels","domain_boundaries_aa","resolved_family","pseudogene_marked"], association_rows)
    domain_instances.sort(key=lambda r:(r["protein_id"],r["method"],int(r["target_start_aa"]),r["model"]))
    write_tsv_atomic(output_dir / "domain_instances.tsv",
        ["protein_id","method","model","family","target_start_aa","target_end_aa","target_length_aa","hmm_start","hmm_end","i_evalue","coverage","support_type"], domain_instances)

    # Per protein/method family roots are used for method agreement; multiple
    # assignments are retained as sets rather than collapsed to a first token.
    method_families: dict[str, dict[str, set[str]]] = {r["Gene ID"]: {k:set() for k,_ in METHOD_COLUMNS} for r in overview}
    overview_map = {r["Gene ID"]: r for r in overview}
    for row in hhm_rows:
        method_families.setdefault(row["Target Name"], {k:set() for k,_ in METHOD_COLUMNS})["dbCAN_hmm"].update(parse_family_roots(row["HMM Name"]))
    for row in sub_rows:
        method_families.setdefault(row["Target Name"], {k:set() for k,_ in METHOD_COLUMNS})["dbCAN_sub"].update(parse_family_roots(row["Subfam Name"]))
    for row in diamond_rows:
        method_families.setdefault(row["Gene ID"], {k:set() for k,_ in METHOD_COLUMNS})["DIAMOND"].update(parse_family_roots(row["CAZy ID"]))
    agreements=[]
    support_dist=Counter()
    resolved_agreement=0
    for pid,row in overview_map.items():
        positive=_positive_method_count(row)
        roots_by_method=[method_families.get(pid,{}).get(k,set()) for k,_ in METHOD_COLUMNS]
        roots=set().union(*roots_by_method)
        family_votes={fam:sum(fam in s for s in roots_by_method) for fam in sorted(roots)}
        agreeing=sorted(fam for fam,n in family_votes.items() if n>=2)
        if agreeing: resolved_agreement+=1
        support_dist[positive]+=1
        agreements.append({"protein_id":pid,"positive_method_count":positive,
            "dbCAN_hmm_families":";".join(sorted(roots_by_method[0])),
            "dbCAN_sub_families":";".join(sorted(roots_by_method[1])),
            "DIAMOND_families":";".join(sorted(roots_by_method[2])),
            "positive_in_at_least_two_methods":positive>=2,
            "resolved_family_agreement":";".join(agreeing),
            "has_resolved_family_agreement":bool(agreeing),
            "pseudogene_marked":pid in pseudo})
    write_tsv_atomic(output_dir / "method_agreement.tsv",
        ["protein_id","positive_method_count","dbCAN_hmm_families","dbCAN_sub_families","DIAMOND_families","positive_in_at_least_two_methods","resolved_family_agreement","has_resolved_family_agreement","pseudogene_marked"], agreements)

    unresolved_by_protein: dict[str, set[str]] = defaultdict(set)
    unresolved_by_method: dict[str, Counter[str]] = defaultdict(Counter)
    for association in associations.values():
        if not association["resolved_family"]:
            unresolved_by_protein[association["protein_id"]].add(association["family"])
            unresolved_by_method[association["method"]][association["family"]] += 1

    # Counts deliberately overlap when one protein has multiple family assignments.
    roots_by_protein: dict[str,set[str]]=defaultdict(set)
    per_family_method_proteins: dict[tuple[str,str],set[str]]=defaultdict(set)
    per_family_agreeing: dict[str,set[str]]=defaultdict(set)
    for pid,methods in method_families.items():
        all_roots=set().union(*methods.values())
        roots_by_protein[pid]=all_roots
        for fam in all_roots:
            for method,roots in methods.items():
                if fam in roots: per_family_method_proteins[(fam,method)].add(pid)
            if sum(fam in roots for roots in methods.values())>=2:
                per_family_agreeing[fam].add(pid)
    query_domain_proteins: dict[str,set[str]]=defaultdict(set)
    domain_count: Counter[str]=Counter()
    for row in domain_instances:
        fam=row["family"]
        if fam and fam not in UNRESOLVED_ROOTS:
            query_domain_proteins[fam].add(row["protein_id"])
            domain_count[fam]+=1
    family_set=sorted({fam for fams in roots_by_protein.values() for fam in fams if fam not in UNRESOLVED_ROOTS})
    family_rows=[]
    for fam in family_set:
        family_rows.append({"sample":faa.stem,"family":fam,"family_class":re.match(r"[A-Z]+",fam).group(0),
            "unique_proteins_any_method":len({pid for pid,fs in roots_by_protein.items() if fam in fs}),
            "proteins_dbCAN_HMM":len(per_family_method_proteins[(fam,"dbCAN_hmm")]),
            "proteins_dbCAN_sub":len(per_family_method_proteins[(fam,"dbCAN_sub")]),
            "proteins_DIAMOND_reference_association":len(per_family_method_proteins[(fam,"DIAMOND")]),
            "proteins_with_resolved_family_agreement":len(per_family_agreeing[fam]),
            "query_aligned_domain_instances":domain_count[fam],
            "query_domain_supported_proteins":len(query_domain_proteins[fam])})
    write_tsv_atomic(output_dir / "family_protein_counts.tsv",
        ["sample","family","family_class","unique_proteins_any_method","proteins_dbCAN_HMM","proteins_dbCAN_sub","proteins_DIAMOND_reference_association","proteins_with_resolved_family_agreement","query_aligned_domain_instances","query_domain_supported_proteins"], family_rows)
    class_counts=[]
    for cls in sorted({r["family_class"] for r in family_rows}):
        fams=[r for r in family_rows if r["family_class"]==cls]
        class_counts.append({"sample":faa.stem,"class":cls,"families_present":len(fams),
            "unique_proteins_any_family_in_class":len({pid for pid,fs in roots_by_protein.items() if any(f.startswith(cls) for f in fs)}),
            "query_aligned_domain_instances":sum(r["query_aligned_domain_instances"] for r in fams),
            "family_counts":";".join(f"{r['family']}={r['unique_proteins_any_method']}" for r in sorted(fams,key=lambda x:(-x["unique_proteins_any_method"],x["family"])))})
    write_tsv_atomic(output_dir / "class_family_comparison.tsv",
        ["sample","class","families_present","unique_proteins_any_family_in_class","query_aligned_domain_instances","family_counts"], class_counts)

    agreement_by_id = {row["protein_id"]: row["resolved_family_agreement"] for row in agreements}
    candidates=[]
    for row in overview:
        pid=row["Gene ID"]
        candidates.append({"protein_id":pid,"methods_positive":_positive_method_count(row),
            "dbCAN_hmm_call":row["dbCAN_hmm"],"dbCAN_sub_call":row["dbCAN_sub"],"DIAMOND_call":row["DIAMOND"],
            "all_family_associations":";".join(sorted(roots_by_protein.get(pid,set()))),
            "unresolved_family_labels":";".join(sorted(unresolved_by_protein.get(pid,set()))),
            "resolved_family_agreement":agreement_by_id.get(pid, ""),
            "domain_boundaries_aa":";".join(sorted({f"{d['method']}:{d['family']}:{d['target_start_aa']}-{d['target_end_aa']}" for d in domain_instances if d["protein_id"]==pid})),
            "pseudogene_marked":pid in pseudo})
    write_tsv_atomic(output_dir / "candidate_evidence.tsv",
        ["protein_id","methods_positive","dbCAN_hmm_call","dbCAN_sub_call","DIAMOND_call","all_family_associations","unresolved_family_labels","resolved_family_agreement","domain_boundaries_aa","pseudogene_marked"], candidates)

    summaries = {"sample":faa.stem,"run_dbcan_version_expected":DBCAN_VERSION,"protein_count":len(proteins),
        "overview_candidate_count":len(overview),"positive_method_count_distribution":dict(sorted(support_dist.items())),
        "positive_in_at_least_two_methods":sum(int(k)>=2 for k,v in support_dist.items() for _ in range(v)),
        "proteins_with_resolved_family_agreement":resolved_agreement,
        "candidates_with_at_least_one_resolved_family":len({pid for pid, families in roots_by_protein.items() if families}),
        "candidates_with_unresolved_family_labels":len(unresolved_by_protein),
        "candidates_with_only_unresolved_family_labels":len({pid for pid in unresolved_by_protein if not roots_by_protein.get(pid)}),
        "unresolved_family_associations_by_method":{
            method: dict(sorted(counts.items())) for method, counts in sorted(unresolved_by_method.items())},
        "unique_resolved_family_count":len(family_set),"family_protein_associations":sum(r["unique_proteins_any_method"] for r in family_rows),
        "query_aligned_domain_instances":len(domain_instances),"pseudogene_cds_count":len(pseudo),
        "pseudogene_candidates":sorted(set(row["protein_id"] for row in candidates if row["pseudogene_marked"])),
        "caution":"protein counts, protein-family associations, and domain instances are separate non-equivalent quantities; DIAMOND labels are reference family associations, not query-domain proof."}
    write_json_atomic(output_dir / "summary.json", summaries)
    return summaries


def effective_resources() -> dict[str, Any]:
    logical = os.cpu_count()
    affinity = None
    if hasattr(os, "sched_getaffinity"):
        try: affinity = len(os.sched_getaffinity(0))
        except OSError: pass
    quota_cpu = None
    for p in (Path("/sys/fs/cgroup/cpu.max"), Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")):
        try:
            text = p.read_text().strip()
            if p.name == "cpu.max":
                quota, period = text.split()[:2]
                if quota != "max": quota_cpu = max(1, int((int(quota)+int(period)-1)//int(period)))
            else:
                quota = int(text)
                if quota > 0:
                    period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip())
                    quota_cpu = max(1, (quota+period-1)//period)
            if quota_cpu: break
        except (OSError, ValueError): pass
    slurm = os.environ.get("SLURM_CPUS_PER_TASK")
    limits = [x for x in (affinity, quota_cpu, int(slurm) if slurm and slurm.isdigit() else None) if x and x > 0]
    effective_cpu = min(limits) if limits else logical
    memory_bytes = None
    memory_source = None
    for p in (Path("/sys/fs/cgroup/memory.max"), Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            value=p.read_text().strip()
            if value != "max" and int(value) < 1 << 60:
                memory_bytes=int(value); memory_source=str(p); break
        except (OSError,ValueError): pass
    if memory_bytes is None:
        try:
            pages=os.sysconf("SC_PHYS_PAGES"); page_size=os.sysconf("SC_PAGE_SIZE")
            memory_bytes=int(pages*page_size); memory_source="sysconf physical memory; no cgroup limit found"
        except (ValueError,OSError,AttributeError): pass
    return {"logical_cpu_count":logical,"cpu_affinity_count":affinity,"cgroup_or_scheduler_cpu_limit":quota_cpu or (int(slurm) if slurm and slurm.isdigit() else None),
            "effective_cpu_allocation":effective_cpu,"memory_limit_bytes":memory_bytes,"memory_source":memory_source,
            "disk_free_bytes_by_path":{}}


def check_fresh_destinations(results_root: Path, metadata_root: Path, samples: Iterable[str], *, resume: bool = False) -> None:
    for sample in samples:
        target = results_root / sample
        if target.exists() and any(target.iterdir()) and not resume:
            raise ExistingPathRefusal('PATHS_OVERLAP', f"results destination is not empty; choose a new --results-dir: {target}")
    if metadata_root.exists() and any(metadata_root.iterdir()) and not resume:
        raise ExistingPathRefusal('PATHS_OVERLAP', f"metadata destination is not empty; choose a new --metadata-dir: {metadata_root}")


def collect_preflight(faa: Path, gff: Path, env_python: Path, run_dbcan_path: Path, diamond_path: Path,
                      db_dir: Path, expected_manifest: Path, threads: int, profile: str,
                      results_dir: Path, metadata_dir: Path) -> dict[str, Any]:
    """Collect safe independent readiness checks without starting search stages."""
    from dbcan_preflight import collect_preflight as collect
    return collect(faa, gff, env_python, run_dbcan_path, diamond_path, db_dir,
        expected_manifest, threads, profile, results_dir, metadata_dir)


def run_preflight(faa: Path, gff: Path, env_python: Path, run_dbcan_path: Path, diamond_path: Path,
                  db_dir: Path, expected_manifest: Path, threads: int, profile: str, results_dir: Path,
                  metadata_dir: Path) -> dict[str, Any]:
    """Strict library facade: return provenance only when all required checks pass."""
    from dbcan_preflight import collect_preflight as collect, require_preflight
    report = collect(faa, gff, env_python, run_dbcan_path, diamond_path, db_dir,
        expected_manifest, threads, profile, results_dir, metadata_dir, stop_on_failure=True)
    require_preflight(report)
    return report


def stage_commands(run_dbcan: Path, faa: Path, local_gff: Path, result_dir: Path, db_dir: Path,
                   threads: int, log_dir: Path, *, env_python: Path | None = None,
                   threadcap_script: Path | None = None) -> list[tuple[str, list[str], Path]]:
    """Build argv arrays for dbCAN 5.2.9 and cap substrate CPU use where its CLI has no threads option."""
    python = str(env_python or Path(sys.executable))
    exe = [python, str(run_dbcan)]
    threadcap = str(threadcap_script or Path(__file__).with_name("run_dbcan_threadcap.py"))
    return [
        ("CAZyme_annotation", [*exe, "CAZyme_annotation", "--mode", "protein", "--input_raw_data", str(faa),
            "--output_dir", str(result_dir), "--db_dir", str(db_dir), "--methods", "diamond,hmm,dbCANsub",
            "--threads", str(threads), "--log-level", "INFO", "--log-file", str(log_dir / "01_cazyme.log")],
            log_dir / "01_cazyme.stdout.log"),
        ("gff_process", [*exe, "gff_process", "--db_dir", str(db_dir), "--output_dir", str(result_dir),
            "--threads", str(threads), "--input_gff", str(local_gff), "--gff_type", "prodigal",
            "--log-level", "INFO", "--log-file", str(log_dir / "02_gff_process.log")],
            log_dir / "02_gff_process.stdout.log"),
        ("cgc_finder", [*exe, "cgc_finder", "--output_dir", str(result_dir), "--log-level", "INFO",
            "--log-file", str(log_dir / "03_cgc_finder.log")], log_dir / "03_cgc_finder.stdout.log"),
        ("substrate_prediction", [python, threadcap, str(threads), "substrate_prediction", "--mode", "protein",
            "--input_raw_data", str(faa), "--output_dir", str(result_dir), "--db_dir", str(db_dir),
            "--log-level", "INFO", "--log-file", str(log_dir / "04_substrate_prediction.log")],
            log_dir / "04_substrate_prediction.stdout.log"),
    ]


def _hash_tree(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def _guard_output_directories(outputs: Iterable[Path], protected: Iterable[Path]) -> None:
    destinations = [p.resolve() for p in outputs]
    protected = [p.resolve() for p in protected]
    for i, left in enumerate(destinations):
        for right in protected + destinations[i + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise Refusal('PATHS_OVERLAP', f"output directories must be disjoint from inputs, runtime, database and each other: {left}; {right}")


def _guard_output_files(outputs: Iterable[Path], protected: Iterable[Path]) -> None:
    destinations = [p.resolve() for p in outputs]
    sources = {p.resolve() for p in protected}
    if len(set(destinations)) != len(destinations) or any(p in sources for p in destinations):
        raise Refusal('PATHS_OVERLAP', "derived output files must be distinct and must not overwrite source files")


def _stage_record(status_file: Path, stage: str, *, state: str, started: str | None = None,
                  exit_code: int | None = None, argv: list[str] | None = None,
                  log_file: Path | None = None, results_dir: Path | None = None,
                  reason: str | None = None) -> None:
    data = json.loads(status_file.read_text(encoding="utf-8"))
    record = data["stages"].setdefault(stage, {})
    record.update({"state": "succeeded" if state == "completed" else state, "status": "succeeded" if state == "completed" else state, "exit_code": exit_code, "ended_utc": utc_now(),
                   "resources_after": effective_resources()})
    if started:
        record["started_utc"] = started
        record["resources_before"] = record.get("resources_before", {})
    if argv is not None:
        record["argv"] = argv
    if log_file is not None:
        record["log_file"] = str(log_file.resolve())
    if results_dir is not None:
        record["output_sha256"] = _hash_tree(results_dir)
    if reason:
        record["reason"] = reason
    write_json_atomic(status_file, _v2_status_document(data))


def run_workflow(input_dir: Path, results_dir: Path, metadata_dir: Path, db_dir: Path,
                 expected_manifest: Path, env_dir: Path, samples: list[str], threads: int,
                 profile: str) -> dict[str, Any]:
    """Run only into fresh explicit destinations; keep each sample's stage ledger separate."""
    input_dir, results_dir, metadata_dir, db_dir, env_dir = [p.resolve() for p in
        (input_dir, results_dir, metadata_dir, db_dir, env_dir)]
    if not samples or len(samples) != len(set(samples)) or any(s in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", s) for s in samples):
        raise Refusal('SAMPLE_ID_UNSAFE', "provide unique sample names containing only letters, digits, period, underscore, or hyphen")
    for left_name, left, right_name, right in (
        ("inputs", input_dir, "results", results_dir), ("inputs", input_dir, "metadata", metadata_dir),
        ("results", results_dir, "metadata", metadata_dir),
    ):
        if left == right or left in right.parents or right in left.parents:
            raise Refusal('PATHS_OVERLAP', f"{left_name} and {right_name} directories must be disjoint: {left}, {right}")
    if not input_dir.is_dir():
        raise MissingPathRefusal('INPUT_MISSING', f"input directory does not exist: {input_dir}")
    _guard_output_directories([results_dir, metadata_dir], [input_dir, db_dir, env_dir])
    for target in (results_dir, metadata_dir):
        if target.resolve() == expected_manifest.resolve() or target.resolve() in expected_manifest.resolve().parents:
            raise Refusal('PATHS_OVERLAP', "run outputs must not overlap the expected database manifest")
    for root in (results_dir, metadata_dir):
        if root.exists() and any(root.iterdir()):
            raise ExistingPathRefusal('PATHS_OVERLAP', f"run destination must be fresh and empty: {root}")
    paired_inputs = {}
    for sample in samples:
        faa = input_dir / "original" / f"{sample}.faa"
        gff = input_dir / "original" / f"{sample}.gff3"
        paired_inputs[sample] = compare_faa_gff(faa, gff)
    batch_run_id = f"dbcan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    env_python, run_dbcan_path, diamond_path = env_dir / "bin/python", env_dir / "bin/run_dbcan", env_dir / "bin/diamond"
    shared_preflight = run_preflight(input_dir / "original" / f"{samples[0]}.faa",
        input_dir / "original" / f"{samples[0]}.gff3", env_python, run_dbcan_path, diamond_path,
        db_dir, expected_manifest, threads, profile, results_dir, metadata_dir)
    if "checks" in shared_preflight:
        from dbcan_preflight import require_preflight
        require_preflight(shared_preflight)
    preflights = {sample: {**shared_preflight,
        "protein_count": len(paired_inputs[sample]["proteins"]),
        "contig_count": len(paired_inputs[sample]["annotation"]["seq_regions"])} for sample in samples}

    failures = []
    sample_summaries = {}
    env = os.environ.copy()
    env["PATH"] = f"{env_dir / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    for sample in samples:
        faa = input_dir / "original" / f"{sample}.faa"
        gff = input_dir / "original" / f"{sample}.gff3"
        result_dir = results_dir / sample
        sample_meta = metadata_dir / sample
        sample_meta.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)
        log_dir = result_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        local_gff = result_dir / "inputs" / f"{sample}.cds.flat.local.gff"
        adapter_report = result_dir / "inputs" / f"{sample}.local_gff_validation.json"
        status_file = sample_meta / "stage_status.json"
        events_file = sample_meta / "events.jsonl"
        run_id = batch_run_id
        status = {"run_id": run_id, "sample": sample, "started_utc": utc_now(),
            "input_faa": str(faa), "input_faa_sha256": sha256_file(faa), "input_gff": str(gff),
            "input_gff_sha256": sha256_file(gff), "results_dir": str(result_dir), "metadata_dir": str(sample_meta),
            "run_dbcan_version": DBCAN_VERSION,
            "database_snapshot": shared_preflight["database"]["manifest_check"]["snapshot"],
            "database_expected_manifest_sha256": sha256_file(expected_manifest), "profile": profile,
            "threads": threads, "stages": {name: {"status": "pending", "exit_code": None} for name in STAGE_NAMES}}
        write_json_atomic(status_file, _v2_status_document({**status, "status": "running"}))
        try:
            append_event(events_file, run_id, sample, None, "run_started")
            prepare_local_gff(faa, gff, local_gff, adapter_report)
            commands = stage_commands(run_dbcan_path, faa, local_gff, result_dir, db_dir, threads, log_dir,
                env_python=env_python, threadcap_script=Path(__file__).with_name("run_dbcan_threadcap.py"))
            for stage, argv, log_file in commands:
                current = json.loads(status_file.read_text(encoding="utf-8"))
                started = utc_now()
                current["stages"][stage] = {"status": "running", "exit_code": None,
                    "started_utc": started, "argv": argv, "resources_before": effective_resources()}
                write_json_atomic(status_file, _v2_status_document(current))
                append_event(events_file, run_id, sample, stage, "stage_started", log_path=str(log_file.resolve()))
                log_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with log_file.open("w", encoding="utf-8") as log_handle:
                        completed = subprocess.run(argv, cwd=result_dir, env=env, stdout=log_handle,
                                                    stderr=subprocess.STDOUT, check=False)
                except OSError as exc:
                    _stage_record(status_file, stage, state="failed", started=started, exit_code=None,
                        argv=argv, log_file=log_file, results_dir=result_dir, reason=f"could not start stage: {exc}")
                    raise StageFailure('STAGE_FAILED', 'An external dbCAN stage could not start.',
                        details=failure_context(sample, stage, None, log_file)) from exc
                _stage_record(status_file, stage, state="succeeded" if completed.returncode == 0 else "failed",
                    started=started, exit_code=completed.returncode, argv=argv,
                    log_file=log_file, results_dir=result_dir,
                    reason=None if completed.returncode == 0 else "dbCAN stage returned a nonzero exit code")
                append_event(events_file, run_id, sample, stage,
                    "stage_succeeded" if completed.returncode == 0 else "stage_failed",
                    exit_code=completed.returncode, log_path=str(log_file.resolve()))
                if completed.returncode != 0:
                    raise StageFailure('STAGE_FAILED', f"{sample} {stage} failed with exit code {completed.returncode}; see {log_file}",
                        details=failure_context(sample, stage, completed.returncode, log_file))
            current = json.loads(status_file.read_text(encoding="utf-8"))
            current["status"] = "stages_succeeded"
            current["run"] = {"state": "stages_succeeded"}
            current["stages_ended_utc"] = utc_now()
            write_json_atomic(status_file, _v2_status_document(current))
            append_event(events_file, run_id, sample, None, "validation_started")
            validation = validate_outputs(faa, gff, result_dir, status_file=status_file,
                require_stage_status=True, observed_manifest=sample_meta / "results_observed.sha256")
            write_json_atomic(sample_meta / "output_validation.json", validation)
            append_event(events_file, run_id, sample, None, "validation_succeeded")
            sample_summaries[sample] = summarize_results(faa, gff, result_dir, sample_meta / "scientific_summary")
            current = json.loads(status_file.read_text(encoding="utf-8"))
            current["status"] = "succeeded"
            current["run"] = {"state": "succeeded"}
            current["completed_utc"] = utc_now()
            write_json_atomic(status_file, _v2_status_document(current))
            write_json_atomic(sample_meta / "completion.json", {"sample": sample, "run_id": run_id,
                "schema_version": 2, "run": {"state": "succeeded"}, "completed_utc": utc_now(), "validation": validation,
                "scientific_summary": sample_summaries[sample]})
            append_event(events_file, run_id, sample, None, "run_succeeded")
        except Exception as exc:
            context = dict(exc.details) if isinstance(exc, StageFailure) else {}
            failures.append({"sample": sample, "error": str(exc), **context})
            (sample_meta / "completion.json").unlink(missing_ok=True)
            try:
                current = json.loads(status_file.read_text(encoding="utf-8"))
                if isinstance(exc, StageFailure) and context.get("exit_code") is None:
                    append_event(events_file, run_id, sample, context.get("stage"), "stage_failed",
                        exit_code=None, log_path=context.get("log_path"))
                for stage in STAGE_NAMES:
                    if current["stages"][stage]["status"] == "pending":
                        append_event(events_file, run_id, sample, stage, "stage_skipped")
                        current["stages"][stage] = {"status": "skipped", "exit_code": None,
                            "reason": "an earlier preflight or stage failed"}
                current["status"] = "failed"
                current["run"] = {"state": "failed"}
                current["failure"] = {"message": str(exc), "ended_utc": utc_now(),
                    "kind": getattr(exc, 'kind', 'error'), "code": getattr(exc, 'code', 'INTERNAL_ERROR'), **context}
                write_json_atomic(status_file, _v2_status_document(current))
            except Exception:
                print('Could not persist failure evidence.', file=sys.stderr)
                try:
                    append_event(events_file, run_id, sample, None, 'evidence_write_failed')
                except Exception:
                    pass
            append_event(events_file, run_id, sample, None, "run_failed",
                kind=getattr(exc, "kind", "error"), code=getattr(exc, "code", "INTERNAL_ERROR"))
            if not isinstance(exc, (StageFailure, NegativeResult)):
                raise
    overall = {"run_id": batch_run_id,
        "status": "complete" if not failures else "failed", "samples": samples,
        "preflight": preflights, "sample_summaries": sample_summaries, "failures": failures}
    write_json_atomic(metadata_dir / "workflow_summary.json", _v2_status_document(overall))
    return overall


# Public command metadata lives beside the parser; describe and docs share it.
COMMAND_METADATA = {
    'prepare': {'summary': 'Validate paired inputs and prepare standalone CDS GFF.', 'writes': ['--out-gff', '--report']},
    'validate': {'summary': 'Validate the exact native results and optional execution attestation.', 'writes': ['output_validation.json', 'results_observed.sha256 (or --observed-manifest)', 'envelope.validate.json']},
    'summarize': {'summary': 'Write overlap-aware scientific evidence tables.', 'writes': ['summary.json', 'protein_family_associations.tsv', 'domain_instances.tsv', 'method_agreement.tsv', 'family_protein_counts.tsv', 'class_family_comparison.tsv', 'candidate_evidence.tsv', 'envelope.summarize.json']},
    'verify-db': {'summary': 'Compare a supplied cache with every expected path and digest.', 'writes': ['--observed-manifest', '--diff-out (optional)']},
    'preflight': {'summary': 'Report every safe readiness check; unmet requirements are a negative result.', 'writes': []},
    'run': {'summary': 'Run four stages only after confirmed preflight into fresh roots.', 'writes': ['native results', 'logs/*', 'inputs/*', 'stage_status.json', 'output_validation.json', 'results_observed.sha256', 'scientific_summary/*', 'completion.json', 'workflow_summary.json', 'events.jsonl (per sample)', 'envelope.run.json']},
    'audit-circular': {'summary': 'Audit circular terminal windows against original topology.', 'writes': ['--out-json', '--out-tsv']},
    'cgc-overlay': {'summary': 'Write a derived exact-category comparison without modifying native tables.', 'writes': ['--corrected-members', '--corrected-summary', '--changes', '--report']},
    'describe': {'summary': 'Describe arguments, effects and the contract without executing work.', 'writes': []},
}


def build_parser():
    from dbcan_cli import ContractParser, global_parent
    parent = global_parent()
    parser = ContractParser(description=__doc__, parents=[parent])
    sub = parser.add_subparsers(dest="command", required=True, help="select an operation")
    prep = sub.add_parser("prepare", parents=[parent], help="validate a Bakta FAA/GFF3 pair and prepare local flat-CDS GFF")
    prep.add_argument("--faa", type=Path, required=True, help='source protein FASTA (input path)')
    prep.add_argument("--gff", type=Path, required=True, help='original Bakta GFF3 (input path)')
    prep.add_argument("--out-gff", type=Path, required=True, help='standalone CDS GFF (output path)')
    prep.add_argument("--report", type=Path, required=True, help='adapter validation JSON (output path)')

    val = sub.add_parser("validate", parents=[parent], help="validate one exact results directory and write separate metadata")
    val.add_argument("--faa", type=Path, required=True, help='source protein FASTA (input path)')
    val.add_argument("--gff", type=Path, required=True, help='original Bakta GFF3 (input path)')
    val.add_argument("--results-dir", type=Path, required=True, help='native results directory; run requires a fresh output root')
    val.add_argument("--metadata-dir", type=Path, required=True, help='separate diagnostics directory (output path)')
    val.add_argument("--status-file", type=Path, help='bound stage_status.json (input path); a supplied rejected record cannot be bypassed')
    val.add_argument("--allow-unattested", action="store_true",
                     help="accept structural validation without claiming successful stage execution")
    val.add_argument("--observed-manifest", type=Path, help='observed SHA256 manifest (output path)')

    val.add_argument('--sample-id', help='explicit isolate label; a label does not verify identity')

    summ = sub.add_parser("summarize", parents=[parent], help="write overlap-aware family/domain tables to separate metadata")
    summ.add_argument("--faa", type=Path, required=True, help='source protein FASTA (input path)')
    summ.add_argument("--gff", type=Path, required=True, help='original Bakta GFF3 (input path)')
    summ.add_argument("--results-dir", type=Path, required=True, help='native results directory; run requires a fresh output root')
    summ.add_argument("--metadata-dir", type=Path, required=True, help='separate diagnostics directory (output path)')

    summ.add_argument('--sample-id', help='explicit isolate label; a label does not verify identity')

    verify = sub.add_parser("verify-db", parents=[parent], help="compare a database directory with a preserved expected manifest")
    verify.add_argument("--db-dir", type=Path, required=True, help='supplied database cache (input path); never downloaded')
    verify.add_argument("--expected-manifest", type=Path, required=True, help='preserved expected SHA256 manifest (input path)')
    verify.add_argument("--observed-manifest", type=Path, required=True, help='observed SHA256 manifest (output path)')

    verify.add_argument('--max-listed', type=int, default=20, help='maximum listed differences per category (default 20; counts remain complete)')
    verify.add_argument('--diff-out', type=Path, help='complete database difference lists (output path)')

    pre = sub.add_parser("preflight", parents=[parent], help="check runtime, input identity, resource budget, and reference assets")
    pre.add_argument("--faa", type=Path, required=True, help='source protein FASTA (input path)')
    pre.add_argument("--gff", type=Path, required=True, help='original Bakta GFF3 (input path)')
    pre.add_argument("--env-dir", type=Path, required=True, help='pinned environment containing bin/python, run_dbcan and diamond (input path)')
    pre.add_argument("--db-dir", type=Path, required=True, help='supplied database cache (input path); never downloaded')
    pre.add_argument("--expected-manifest", type=Path, required=True, help='preserved expected SHA256 manifest (input path)')
    pre.add_argument("--threads", type=int, required=True, help='positive CPU budget within the detected allocation')
    pre.add_argument("--profile", choices=("sandbox", "hpc"), required=True, help='explicit resource profile')
    pre.add_argument("--results-dir", type=Path, required=True, help='native results directory; run requires a fresh output root')
    pre.add_argument("--metadata-dir", type=Path, required=True, help='separate diagnostics directory (output path)')

    run = sub.add_parser("run", parents=[parent], help="run all dbCAN stages with explicit roots, verified assets, and per-stage records")
    run.add_argument("--input-dir", type=Path, required=True, help='input root with original/SAMPLE.faa and original/SAMPLE.gff3')
    run.add_argument("--results-dir", type=Path, required=True, help='native results directory; run requires a fresh output root')
    run.add_argument("--metadata-dir", type=Path, required=True, help='separate diagnostics directory (output path)')
    run.add_argument("--db-dir", type=Path, required=True, help='supplied database cache (input path); never downloaded')
    run.add_argument("--expected-manifest", type=Path, required=True, help='preserved expected SHA256 manifest (input path)')
    run.add_argument("--env-dir", type=Path, required=True, help='pinned environment containing bin/python, run_dbcan and diamond (input path)')
    run.add_argument("--samples", nargs="+", required=True, help='unique safe isolate names')
    run.add_argument("--threads", type=int, required=True, help='positive CPU budget within the detected allocation')
    run.add_argument("--profile", choices=("sandbox", "hpc"), required=True, help='explicit resource profile')

    audit = sub.add_parser('audit-circular', parents=[parent], help='audit original topology and terminal signature windows')
    audit.add_argument('--gff', type=Path, required=True, help='original Bakta GFF3 with topology (input path)')
    audit.add_argument('--processed-gff', type=Path, required=True, help='native dbCAN cgc.gff (input path)')
    audit.add_argument('--out-json', '--json', dest='out_json', type=Path, required=True, help='circular audit JSON (output path); --json is deprecated')
    audit.add_argument('--out-tsv', '--tsv', dest='out_tsv', type=Path, required=True, help='circular audit TSV (output path); --tsv is deprecated')
    overlay = sub.add_parser('cgc-overlay', parents=[parent], help='write a version-guarded exact-category overlay')
    for flag, help_text in (
        ('--processed-gff', 'native dbCAN cgc.gff (input path)'),
        ('--native-members', 'native CGC membership table (input path)'),
        ('--native-summary', 'native CGC summary table (input path)'),
        ('--corrected-members', 'derived membership table (output path)'),
        ('--corrected-summary', 'derived summary table (output path)'),
        ('--changes', 'membership and boundary differences (output path)'),
        ('--report', 'overlay report JSON (output path)'),
    ):
        overlay.add_argument(flag, type=Path, required=True, help=help_text)
    overlay.add_argument('--dbcan-version', required=True, help='caller-supplied compatibility guard, not runtime evidence (must be 5.2.9)')
    overlay.add_argument('--use-distance', action='store_true', help='enable the mirrored 15000 bp distance rule')

    desc = sub.add_parser('describe', parents=[parent], help=COMMAND_METADATA['describe']['summary'])
    desc.add_argument('--format', choices=('json', 'markdown'), default='json', help='include JSON metadata or a Markdown rendering inside result')
    examples = {
        'audit-circular': 'audit-circular --gff inputs/sample.gff3 --processed-gff native/cgc.gff --out-json derived/circular.json --out-tsv derived/circular.tsv',
        'cgc-overlay': 'cgc-overlay --processed-gff native/cgc.gff --native-members native/cgc_standard_out.tsv --native-summary native/cgc_standard_out_summary.tsv --corrected-members derived/members.tsv --corrected-summary derived/summary.tsv --changes derived/changes.tsv --report derived/report.json --dbcan-version 5.2.9',
        'describe': 'describe --format json',
        'prepare': 'prepare --faa inputs/sample.faa --gff inputs/sample.gff3 --out-gff derived/sample.gff --report derived/adapter.json',
        'validate': 'validate --faa inputs/sample.faa --gff inputs/sample.gff3 --results-dir native/sample --metadata-dir diagnostics/sample --allow-unattested',
        'summarize': 'summarize --faa inputs/sample.faa --gff inputs/sample.gff3 --results-dir native/sample --metadata-dir diagnostics/summary',
        'verify-db': 'verify-db --db-dir cache --expected-manifest environment/database_v5-2-9_5-5-2026.expected.sha256 --observed-manifest diagnostics/cache.sha256',
        'preflight': 'preflight --faa inputs/sample.faa --gff inputs/sample.gff3 --env-dir runtime --db-dir cache --expected-manifest expected.sha256 --threads 1 --profile sandbox --results-dir fresh/results --metadata-dir fresh/metadata',
        'run': 'run --input-dir inputs --results-dir fresh/results --metadata-dir fresh/metadata --db-dir cache --expected-manifest expected.sha256 --env-dir runtime --samples sample --threads 1 --profile sandbox',
    }
    for name, command_parser in sub.choices.items():
        command_parser.epilog = 'Example: '+examples[name]
    val.description = 'Validate structure and optional attestation; writes output_validation.json, results_observed.sha256 and envelope.validate.json to separate metadata.'
    verify.description = 'Compare every database asset; writes the observed manifest to --observed-manifest.'
    pre.description = 'Report independent readiness checks; unmet requirements produce negative/PREFLIGHT_UNMET. Unsafe paths are refused before probes. No files are written unless --envelope-out is supplied.'
    run.description = 'Require strict preflight before starting stages. Append per-sample events in metadata; retain stage logs under native results and include bounded excerpts on failure.'
    parser.epilog = 'Examples: '+ '; '.join(examples.values())
    return parser


def main(argv=None):
    from dbcan_cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
