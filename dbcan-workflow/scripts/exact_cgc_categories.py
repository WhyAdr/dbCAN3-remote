#!/usr/bin/env python3
"""Version-guarded exact-category CGC rebuild for run_dbcan 5.2.9 outputs.

The parser and grouping rules below mirror the released 5.2.9 CGCFinder defaults
used by the baseline. Only category membership changes: category tokens are
parsed as the field before the first '|' in each '+'-separated annotation.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dbcan_workflow import parse_attributes, read_tsv, write_json_atomic, write_tsv_atomic, CGC_HEADER, CGC_SUMMARY_HEADER, _guard_output_files


SUPPORTED_VERSION = "5.2.9"
CORE_TYPES = {"CAZyme"}
PRIORITY = {"CAZyme": 0, "TC": 1, "TF": 2, "STP": 3, "Sulfatase": 4, "Peptidase": 5}
SUMMARY_HEADER = CGC_SUMMARY_HEADER


def categories(annotation: str) -> set[str]:
    """Return exact annotation category tokens; `TF|GLTC_BACSU` maps to TF."""
    found: set[str] = set()
    for component in (annotation or "null").split("+"):
        component = component.strip()
        if not component:
            continue
        found.add(component.split("|", 1)[0].strip())
    return found


def gene_type(annotation: str) -> str:
    types = categories(annotation)
    if not types or types == {"null"}:
        return "null"
    return sorted(types, key=lambda t: (PRIORITY.get(t, 99), t))[0]


def read_processed_gff(path: Path) -> dict[str, list[dict[str, Any]]]:
    by_contig: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) != 9:
            raise ValueError(f"expected 9 columns in {path}:{line_no}")
        if cols[2] != "CDS":
            continue
        attrs = parse_attributes(cols[8])
        pid = attrs.get("protein_id") or attrs.get("ID")
        if not pid:
            raise ValueError(f"no protein_id/ID in {path}:{line_no}")
        if pid in seen:
            raise ValueError(f"duplicate protein ID in processed GFF: {pid}")
        seen.add(pid)
        by_contig[cols[0]].append({"contig": cols[0], "start": int(cols[3]), "end": int(cols[4]),
            "strand": cols[6], "protein_id": pid, "annotation": attrs.get("CGC_annotation", "null"),
            "categories": categories(attrs.get("CGC_annotation", "null"))})
    for rows in by_contig.values():
        rows.sort(key=lambda x: (x["start"], x["end"]))
    return by_contig


def identify_clusters(by_contig: dict[str, list[dict[str, Any]]], *, additional_genes: tuple[str, ...] = ("TC",),
                      max_null_genes: int = 2, min_core_cazyme: int = 1, min_cluster_genes: int = 2,
                      additional_logic: str = "all", additional_min_categories: int = 1,
                      use_distance: bool = False, base_pair_distance: int = 15000) -> list[list[dict[str, Any]]]:
    if additional_logic not in {"all", "any"}:
        raise ValueError("additional_logic must be all or any")
    clusters: list[list[dict[str, Any]]] = []
    for contig in sorted(by_contig):
        rows = by_contig[contig]
        sig_positions = [i for i, row in enumerate(rows)
                         if CORE_TYPES.intersection(row["categories"]) or set(additional_genes).intersection(row["categories"])]
        if len(sig_positions) < 2:
            continue
        start_i = last_i = None
        for sig_i, pos in enumerate(sig_positions):
            if last_i is None:
                start_i = last_i = sig_i
                continue
            pos_last = sig_positions[last_i]
            gap = max(0, pos - pos_last - 1)
            distance_ok = (not use_distance or rows[pos]["start"] - rows[pos_last]["end"] <= base_pair_distance)
            gap_ok = gap <= max_null_genes
            if gap_ok and distance_ok:
                last_i = sig_i
            else:
                assert start_i is not None
                window = rows[sig_positions[start_i]:sig_positions[last_i] + 1]
                if _valid(window, additional_genes, min_core_cazyme, min_cluster_genes, additional_logic, additional_min_categories):
                    clusters.append(window)
                start_i = last_i = sig_i
        if start_i is not None and last_i is not None:
            window = rows[sig_positions[start_i]:sig_positions[last_i] + 1]
            if _valid(window, additional_genes, min_core_cazyme, min_cluster_genes, additional_logic, additional_min_categories):
                clusters.append(window)
    return clusters


def _valid(window: list[dict[str, Any]], additional_genes: tuple[str, ...], min_core: int, min_genes: int,
           logic: str, min_categories: int) -> bool:
    if len(window) < max(1, min_genes):
        return False
    core_count = sum(bool(CORE_TYPES.intersection(row["categories"])) for row in window)
    if core_count < min_core:
        return False
    additional = set().union(*(row["categories"].intersection(additional_genes) for row in window))
    if not additional_genes:
        return True
    if logic == "all":
        return set(additional_genes).issubset(additional)
    return len(additional) >= max(1, min_categories)


def membership_rows(clusters: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out=[]
    for cgc_i, members in enumerate(clusters, 1):
        cid=f"CGC{cgc_i}"
        for gene in members:
            out.append({"CGC#":cid,"Gene Type":gene_type(gene["annotation"]),"Contig ID":gene["contig"],
                "Protein ID":gene["protein_id"],"Gene Start":gene["start"],"Gene Stop":gene["end"],
                "Gene Strand":gene["strand"],"Gene Annotation":gene["annotation"]})
    return out


def summary_rows(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by=defaultdict(list)
    for row in members: by[row["CGC#"]].append(row)
    output=[]
    for cid, rows in by.items():
        contigs={r["Contig ID"] for r in rows}
        if len(contigs)!=1: raise ValueError(f"CGC spans multiple contigs: {cid}")
        start=min(int(r["Gene Start"]) for r in rows); end=max(int(r["Gene Stop"]) for r in rows)
        counts=Counter(r["Gene Type"] for r in rows)
        output.append({"CGC#":cid,"Contig ID":next(iter(contigs)),"Cluster Start":start,"Cluster End":end,
            "Genes":len(rows),"CAZymes":counts["CAZyme"],"TC":counts["TC"],"TF":counts["TF"],
            "STP":counts["STP"],"Sulfatase":counts["Sulfatase"],"Peptidase":counts["Peptidase"],
            "Signatures":sum(v for k,v in counts.items() if k!="null"),"Length (bp)":end-start+1})
    return output


def rebuild(processed_gff: Path, native_members_file: Path, native_summary_file: Path,
            corrected_members_file: Path, corrected_summary_file: Path, change_file: Path,
            report_file: Path, installed_version: str, *, use_distance: bool = False) -> dict[str, Any]:
    if installed_version != SUPPORTED_VERSION:
        raise ValueError(f"exact-category compatibility rebuild is version-guarded for dbCAN {SUPPORTED_VERSION}; got {installed_version}")
    _guard_output_files([corrected_members_file, corrected_summary_file, change_file, report_file],
                        [processed_gff, native_members_file, native_summary_file])
    by=read_processed_gff(processed_gff)
    clusters=identify_clusters(by,use_distance=use_distance)
    members=membership_rows(clusters)
    summaries=summary_rows(members)
    native=read_tsv(native_members_file,CGC_HEADER)
    native_summaries=read_tsv(native_summary_file,SUMMARY_HEADER)
    old_by=defaultdict(list); new_by=defaultdict(list)
    for row in native: old_by[row["CGC#"]].append(row["Protein ID"])
    for row in members: new_by[row["CGC#"]].append(row["Protein ID"])
    changes=[]
    for cid in sorted(set(old_by)|set(new_by), key=lambda x:int(x.removeprefix("CGC"))):
        old=old_by.get(cid,[]); new=new_by.get(cid,[])
        if old!=new:
            old_summary=next((r for r in native_summaries if r["CGC#"]==cid),{})
            new_summary=next((r for r in summaries if r["CGC#"]==cid),{})
            changes.append({"cgc_id":cid,"change":"membership_and_or_boundary_changed","native_member_count":len(old),
                "corrected_member_count":len(new),"native_first_member":old[0] if old else "",
                "corrected_first_member":new[0] if new else "","native_start":old_summary.get("Cluster Start",""),
                "corrected_start":new_summary.get("Cluster Start",""),"native_end":old_summary.get("Cluster End",""),
                "corrected_end":new_summary.get("Cluster End",""),"native_member_ids":";".join(old),
                "corrected_member_ids":";".join(new),"native_only_ids":";".join(x for x in old if x not in new),
                "corrected_only_ids":";".join(x for x in new if x not in old)})
    write_tsv_atomic(corrected_members_file,CGC_HEADER,members)
    write_tsv_atomic(corrected_summary_file,SUMMARY_HEADER,summaries)
    write_tsv_atomic(change_file,["cgc_id","change","native_member_count","corrected_member_count","native_first_member","corrected_first_member","native_start","corrected_start","native_end","corrected_end","native_member_ids","corrected_member_ids","native_only_ids","corrected_only_ids"],changes)
    report={"dbcan_version_guard":SUPPORTED_VERSION,"dbcan_version_supplied":installed_version,
        "source_gff":str(processed_gff.resolve()),"rule":"exact category field before first pipe in each plus-separated CGC_annotation component",
        "parameters":{"core_types":["CAZyme"],"additional_genes":["TC"],"additional_logic":"all","max_null_genes":2,
            "min_core_cazyme":1,"min_cluster_genes":2,"use_distance":use_distance,"extend_mode":"none"},
        "native_cgc_count":len(old_by),"corrected_cgc_count":len(new_by),"native_member_rows":len(native),
        "corrected_member_rows":len(members),"changed_cgcs":changes}
    write_json_atomic(report_file,report)
    return report


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--processed-gff",type=Path,required=True)
    p.add_argument("--native-members",type=Path,required=True)
    p.add_argument("--native-summary",type=Path,required=True)
    p.add_argument("--corrected-members",type=Path,required=True)
    p.add_argument("--corrected-summary",type=Path,required=True)
    p.add_argument("--changes",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--dbcan-version",required=True)
    p.add_argument("--use-distance",action="store_true")
    a=p.parse_args()
    result=rebuild(a.processed_gff,a.native_members,a.native_summary,a.corrected_members,a.corrected_summary,
        a.changes,a.report,a.dbcan_version,use_distance=a.use_distance)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
