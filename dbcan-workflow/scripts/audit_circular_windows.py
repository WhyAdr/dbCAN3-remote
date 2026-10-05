#!/usr/bin/env python3
"""Audit default CAZyme+TC cluster windows at circular contig joins."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from dbcan_workflow import parse_attributes, parse_gff, write_json_atomic, write_tsv_atomic
from exact_cgc_categories import categories


def audit(faa_gff: Path, processed_gff: Path) -> dict[str, Any]:
    annotation = parse_gff(faa_gff)
    by_contig: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for line_no, line in enumerate(processed_gff.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) != 9:
            raise ValueError(f"expected 9 GFF columns at {processed_gff}:{line_no}")
        if cols[2] != "CDS":
            continue
        attrs = parse_attributes(cols[8])
        pid = attrs.get("protein_id") or attrs.get("ID")
        if not pid or pid in seen:
            raise ValueError(f"missing or duplicate processed protein ID at {processed_gff}:{line_no}")
        seen.add(pid)
        if pid not in annotation["cds"]:
            raise ValueError(f"unknown processed protein ID {pid!r}")
        source = annotation["cds"][pid]
        observed = (cols[0], int(cols[3]), int(cols[4]), cols[6])
        expected = (source["seqid"], source["start"], source["end"], source["strand"])
        if observed != expected:
            raise ValueError(f"processed coordinates differ for {pid}: {observed} != {expected}")
        anno = attrs.get("CGC_annotation", "null")
        by_contig[cols[0]].append({"protein_id": pid, "start": int(cols[3]), "end": int(cols[4]),
            "categories": categories(anno), "annotation": anno})
    if seen != set(annotation["cds"]):
        raise ValueError(f"processed GFF CDS ID set differs from input; missing={len(set(annotation['cds'])-seen)}")

    rows = []
    origins = []
    for contig in sorted(annotation["seq_regions"]):
        length = annotation["seq_regions"][contig]
        circular = annotation["circular"].get(contig, False)
        genes = sorted(by_contig.get(contig, []), key=lambda x: (x["start"], x["end"]))
        for gene in genes:
            if gene["end"] > length:
                origins.append({"contig": contig, "protein_id": gene["protein_id"],
                    "start": gene["start"], "end": gene["end"], "contig_length": length,
                    "cds_interval_bp": gene["end"] - gene["start"] + 1,
                    "wrap_bp": gene["end"] - length})
        signature_indices = [i for i, gene in enumerate(genes)
            if "CAZyme" in gene["categories"] or "TC" in gene["categories"]]
        core_total = sum("CAZyme" in gene["categories"] for gene in genes)
        tc_total = sum("TC" in gene["categories"] for gene in genes)
        if len(signature_indices) >= 2:
            first_i, last_i = signature_indices[0], signature_indices[-1]
            gap = (first_i + len(genes) - last_i - 1) if circular else None
            # Include both endpoint signatures and their connected linear
            # windows. Endpoint-only checks can miss a core gene just upstream
            # of a terminal TC signature.
            terminal = []
            if circular and gap <= 2:
                suffix = len(signature_indices) - 1
                while suffix > 0 and signature_indices[suffix] - signature_indices[suffix - 1] - 1 <= 2:
                    suffix -= 1
                prefix = 0
                while prefix + 1 < len(signature_indices) and signature_indices[prefix + 1] - signature_indices[prefix] - 1 <= 2:
                    prefix += 1
                if signature_indices[suffix] <= signature_indices[prefix]:
                    terminal = genes[:]  # One connected circular component; no duplicate genes.
                else:
                    terminal = genes[signature_indices[suffix]:] + genes[:signature_indices[prefix] + 1]
            terminal_core = sum("CAZyme" in gene["categories"] for gene in terminal)
            terminal_tc = sum("TC" in gene["categories"] for gene in terminal)
            terminal_candidate = bool(circular and gap is not None and gap <= 2
                and terminal_core >= 1 and terminal_tc >= 1 and len(terminal) >= 2)
            first_id, last_id = genes[first_i]["protein_id"], genes[last_i]["protein_id"]
        else:
            gap = None
            terminal_core = terminal_tc = 0
            terminal_candidate = False
            first_id = last_id = ""
        rows.append({"contig": contig, "length_bp": length, "is_circular": circular,
            "cds_count": len(genes), "CAZyme_core_count": core_total, "TC_signature_count": tc_total,
            "first_terminal_signature": first_id, "last_terminal_signature": last_id,
            "null_CDS_between_last_and_first": gap, "terminal_window_CAZyme_count": terminal_core,
            "terminal_window_TC_count": terminal_tc, "default_wraparound_CGC_indicated": terminal_candidate,
            "terminal_window_protein_ids": [g["protein_id"] for g in terminal] if len(signature_indices) >= 2 else []})
    return {"source_gff": str(faa_gff.resolve()), "processed_gff": str(processed_gff.resolve()),
        "rules": {"core": "exact CAZyme category", "additional": "exact TC category",
            "maximum_null_cds_between_signatures": 2, "minimum_core_cazymes": 1,
            "linear_clusterer_wraps_origin": False},
        "contigs": rows, "origin_spanning_cds": origins}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gff", type=Path, required=True, help="original Bakta GFF3 with region topology")
    parser.add_argument("--processed-gff", type=Path, required=True, help="dbCAN cgc.gff output")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()
    data = audit(args.gff, args.processed_gff)
    write_json_atomic(args.json, data)
    fields = ["contig", "length_bp", "is_circular", "cds_count", "CAZyme_core_count", "TC_signature_count",
        "first_terminal_signature", "last_terminal_signature", "null_CDS_between_last_and_first",
        "terminal_window_CAZyme_count", "terminal_window_TC_count", "default_wraparound_CGC_indicated"]
    write_tsv_atomic(args.tsv, fields, data["contigs"])
    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
