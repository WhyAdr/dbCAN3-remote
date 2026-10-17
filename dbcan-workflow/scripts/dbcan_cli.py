"""CLI adapters; library dictionaries remain compatible with v0.2.0 callers."""
from __future__ import annotations
import json
from pathlib import Path
import dbcan_workflow as w
from dbcan_outcomes import CommandResult, Refusal


def dispatch(r):
    if r.command == 'prepare':
        data = w.prepare_local_gff(r.faa, r.gff, r.out_gff, r.report)
    elif r.command == 'validate':
        results, metadata = r.results_dir.resolve(), r.metadata_dir.resolve()
        w._guard_output_directories([metadata], [results, r.faa.parent, r.gff.parent])
        data = w.validate_outputs(r.faa, r.gff, results, status_file=r.status_file,
            require_stage_status=not r.allow_unattested,
            observed_manifest=r.observed_manifest or metadata / 'results_observed.sha256')
        w.write_json_atomic(metadata / 'output_validation.json', data)
    elif r.command == 'summarize':
        data = w.summarize_results(r.faa, r.gff, r.results_dir, r.metadata_dir)
    elif r.command == 'verify-db':
        data = w.verify_database(r.db_dir, r.expected_manifest, r.observed_manifest)
    elif r.command == 'preflight':
        env = r.env_dir.resolve()
        data = w.run_preflight(r.faa, r.gff, env/'bin/python', env/'bin/run_dbcan', env/'bin/diamond',
            r.db_dir, r.expected_manifest, r.threads, r.profile, r.results_dir, r.metadata_dir)
    else:
        data = w.run_workflow(r.input_dir, r.results_dir, r.metadata_dir, r.db_dir,
            r.expected_manifest, r.env_dir, r.samples, r.threads, r.profile)
    result = dict(data)
    if 'status' in result:
        result['legacy_status'] = result.pop('status')
    cr = CommandResult(result=result)
    if r.command in {'validate', 'summarize'}:
        cr.evidence = {'structure': 'valid', 'attestation': 'attested' if data.get('execution_attested') else 'unattested'}
        if cr.evidence['attestation'] == 'attested':
            cr.run_id = w._status_check(r.status_file, True, faa=r.faa, gff=r.gff, results_dir=r.results_dir)['run_id']
        cr.summary = 'Structurally valid; execution %s.' % cr.evidence['attestation']
    if r.command == 'verify-db' and not data['match']:
        cr.kind, cr.code, cr.summary = 'negative', 'DB_MISMATCH', 'Database cache does not match the expected manifest.'
    if r.command == 'run':
        cr.run_id = data['run_id']
        if data['status'] != 'complete':
            cr.kind, cr.code, cr.summary = 'failed', 'STAGE_FAILED', 'Workflow did not complete; inspect the stage logs.'
        else:
            cr.evidence = {'structure': 'valid', 'attestation': 'attested'}
    return cr
