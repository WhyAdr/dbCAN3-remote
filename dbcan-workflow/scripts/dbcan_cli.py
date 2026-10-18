"""CLI adapters; library dictionaries remain compatible with v0.2.0 callers."""
from __future__ import annotations
import json
from pathlib import Path
import argparse
import os
import re
import sys
import traceback
import dbcan_workflow as w
from dbcan_outcomes import (CommandResult, Refusal, MissingPathRefusal, EXIT_CODES,
                            REGISTRY, WorkflowOutcome, UsageError)
from dbcan_claims import derive_claims
from dbcan_trust import (assert_trusted, bound_diagnostics, UNTRUSTED_PATHS, WARNINGS_REGISTRY, bounded_details, sanitize_data)


def dispatch(r):
    if r.command == 'describe':
        data = describe_commands()
        if r.format == 'markdown': data['markdown'] = commands_markdown(data)
    elif r.command == 'prepare':
        data = w.prepare_local_gff(r.faa, r.gff, r.out_gff, r.report)
    elif r.command == 'validate':
        results, metadata = r.results_dir.resolve(), r.metadata_dir.resolve()
        w._guard_output_directories([metadata], [results, r.faa.parent, r.gff.parent])
        data = w.validate_outputs(r.faa, r.gff, results, status_file=r.status_file,
            require_stage_status=not r.allow_unattested,
            observed_manifest=r.observed_manifest or metadata / 'results_observed.sha256')
    elif r.command == 'summarize':
        data = w.summarize_results(r.faa, r.gff, r.results_dir, r.metadata_dir)
    elif r.command == 'verify-db':
        if r.max_listed < 0: raise UsageError('USAGE_INVALID', '--max-listed must be nonnegative.')
        data = w.verify_database(r.db_dir, r.expected_manifest, r.observed_manifest)
        differences = {key: data.pop(key) for key in ('missing', 'unexpected', 'mismatched')}
        if r.diff_out: w.write_json_atomic(r.diff_out, differences)
        data.update({key+'_count': len(value) for key, value in differences.items()})
        data['listed'] = {key: value[:r.max_listed] for key, value in differences.items()}
        data['listed_truncated'] = any(len(value)>r.max_listed for value in differences.values())
        data['max_listed'] = r.max_listed
    elif r.command == 'preflight':
        env = r.env_dir.resolve()
        data = w.collect_preflight(r.faa, r.gff, env/'bin/python', env/'bin/run_dbcan', env/'bin/diamond',
            r.db_dir, r.expected_manifest, r.threads, r.profile, r.results_dir, r.metadata_dir)
    elif r.command == 'audit-circular':
        from audit_circular_windows import audit
        data = audit(r.gff, r.processed_gff)
        w.write_json_atomic(r.out_json, data)
        fields = ['contig', 'length_bp', 'is_circular', 'cds_count', 'CAZyme_core_count', 'TC_signature_count',
            'first_terminal_signature', 'last_terminal_signature', 'null_CDS_between_last_and_first',
            'terminal_window_CAZyme_count', 'terminal_window_TC_count', 'default_wraparound_CGC_indicated']
        w.write_tsv_atomic(r.out_tsv, fields, data['contigs'])
    elif r.command == 'cgc-overlay':
        from exact_cgc_categories import rebuild
        data = rebuild(r.processed_gff, r.native_members, r.native_summary, r.corrected_members,
            r.corrected_summary, r.changes, r.report, r.dbcan_version, use_distance=r.use_distance)
    else:
        data = w.run_workflow(r.input_dir, r.results_dir, r.metadata_dir, r.db_dir,
            r.expected_manifest, r.env_dir, r.samples, r.threads, r.profile)
    result = dict(data)
    if 'status' in result:
        result['legacy_status'] = result.pop('status')
    cr = CommandResult(result=result)
    if r.command in {'validate', 'summarize'}:
        sample_id = getattr(r, 'sample_id', None)
        result['sample_source'] = 'explicit' if sample_id is not None else 'faa_stem'
        result['sample'] = sample_id if sample_id is not None else r.faa.stem
        if sample_id is None:
            cr.warnings.append({'code': 'SAMPLE_INFERRED', 'message': WARNINGS_REGISTRY['SAMPLE_INFERRED'], 'location': None})
        if r.command == 'validate': w.write_json_atomic(r.metadata_dir/'output_validation.json', {**data, 'sample': result['sample'], 'sample_source': result['sample_source']})
        else:
            result['substrate_rows'] = len(w.read_tsv(r.results_dir/'substrate_prediction.tsv', w.SUBSTRATE_HEADER))
            w.write_json_atomic(r.metadata_dir/'summary.json', {**data, 'sample': result['sample'], 'sample_source': result['sample_source']})
    if r.command in {'validate', 'summarize'}:
        cr.evidence = {'structure': 'valid', 'attestation': 'attested' if data.get('execution_attested') else 'unattested'}
        if cr.evidence['attestation'] == 'attested':
            cr.run_id = data['run_id']
        cr.summary = 'Structurally valid; execution %s.' % cr.evidence['attestation']
    if r.command == 'preflight' and not data['ready']:
        cr.kind, cr.code, cr.summary = 'negative', 'PREFLIGHT_UNMET', 'Preflight report completed; required checks did not all pass.'
        cr.findings = [{'code': row['detail']['code'], 'message': REGISTRY[row['detail']['code']]['summary'], 'location': row['id']}
            for row in data['checks'] if row['state']=='fail']
    if r.command == 'verify-db' and not data['match']:
        cr.kind, cr.code, cr.summary = 'negative', 'DB_MISMATCH', 'Database cache does not match the expected manifest.'
    if r.command == 'run':
        cr.run_id = data['run_id']
        if data['status'] != 'complete':
            cr.kind, cr.code, cr.summary = 'failed', 'STAGE_FAILED', 'Workflow did not complete; inspect the stage logs.'
            failures = [json.loads((r.metadata_dir/sample/'stage_status.json').read_text()).get('failure', {}) for sample in data['samples'] if (r.metadata_dir/sample/'stage_status.json').exists()]
            if any(failure.get('kind') == 'negative' for failure in failures):
                cr.kind, cr.code = 'negative', 'STRUCTURE_INVALID'
                cr.evidence['structure'] = 'invalid'
                cr.findings = [{'code': cr.code, 'message': REGISTRY[cr.code]['summary'], 'location': None} for failure in failures if failure.get('kind') == 'negative']
        else:
            cr.evidence = {'structure': 'valid', 'attestation': 'attested'}
    return cr

# The stdout contract is emitted once, after execution and guarded persistence.


class ContractParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        raise UsageError('USAGE_INVALID', message)


def global_parent():
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument('--exit-policy', choices=('strict', 'semantic-zero'), default=argparse.SUPPRESS,
        help='process exit projection (default: DBCAN_WORKFLOW_EXIT_POLICY or strict)')
    parent.add_argument('--envelope-out', type=Path, default=argparse.SUPPRESS,
        help='persist the JSON envelope (output path)')
    return parent


def run_metadata_outputs(r):
    """Declare owned metadata slots before accepting a separate envelope path."""
    paths = {}
    for sample in r.samples:
        try:
            w.validate_sample_id(sample)
        except Refusal:
            continue  # The runner retains SAMPLE_ID_UNSAFE classification.
        root = r.metadata_dir/sample
        for name, role in (('events.jsonl', 'event_log'), ('stage_status.json', 'stage_status'),
            ('output_validation.json', 'output_validation'), ('results_observed.sha256', 'observed_manifest'),
            ('completion.json', 'completion')):
            paths[str((root/name).resolve())] = role
        for name in w.COMMAND_METADATA['summarize']['writes']:
            if name.endswith(('.json', '.tsv')) and not name.startswith('envelope.'):
                paths[str((root/'scientific_summary'/name).resolve())] = 'scientific_summary'
    paths[str((r.metadata_dir/'workflow_summary.json').resolve())] = 'workflow_summary'
    return paths


def planned_outputs(r):
    outputs = {}
    def add(path, role):
        if path is not None: outputs[str(path.resolve())] = role
    if r.command == 'prepare':
        add(r.out_gff, 'local_gff'); add(r.report, 'adapter_report')
    elif r.command == 'validate':
        add(r.metadata_dir/'output_validation.json', 'output_validation')
        add(r.observed_manifest or r.metadata_dir/'results_observed.sha256', 'observed_manifest')
    elif r.command == 'verify-db':
        add(r.observed_manifest, 'observed_manifest'); add(getattr(r, 'diff_out', None), 'database_diff')
    if r.command == 'audit-circular':
        add(r.out_json, 'circular_audit'); add(r.out_tsv, 'circular_table')
    if r.command == 'run': outputs.update(run_metadata_outputs(r))
    if r.command == 'summarize':
        for name in w.COMMAND_METADATA['summarize']['writes']:
            if '/' not in name and not name.startswith('--'): add(r.metadata_dir/name, 'scientific_summary')
    if r.command == 'cgc-overlay':
        for key in ('corrected_members', 'corrected_summary', 'changes', 'report'): add(getattr(r, key), key)
    if r.command in {'validate', 'summarize', 'run'}:
        add(r.metadata_dir/('envelope.%s.json' % r.command), 'envelope')
    add(getattr(r, 'envelope_out', None), 'envelope')
    return outputs


def protected_paths(r):
    roots = [getattr(r, key) for key in ('input_dir', 'db_dir', 'env_dir') if getattr(r, key, None)]
    if r.command != 'run' and getattr(r, 'results_dir', None): roots.append(r.results_dir)
    roots += [getattr(r, key).resolve().parent for key in ('faa', 'gff') if getattr(r, key, None)]
    files = [getattr(r, key) for key in ('faa', 'gff', 'expected_manifest', 'status_file', 'processed_gff', 'native_members', 'native_summary') if getattr(r, key, None)]
    roots += [getattr(r, key).resolve().parent for key in ('processed_gff', 'native_members', 'native_summary') if getattr(r, key, None)]
    return roots, files


def guard_cli_outputs(r):
    roots, files = protected_paths(r)
    paths = planned_outputs(r)
    # Preserve output-slot distinctions before the inventory dict deduplicates paths.
    selected = []
    if r.command == 'prepare': selected = [r.out_gff, r.report]
    elif r.command == 'validate': selected = [r.metadata_dir/'output_validation.json', r.observed_manifest or r.metadata_dir/'results_observed.sha256']
    elif r.command == 'summarize': selected = [r.metadata_dir/name for name in w.COMMAND_METADATA['summarize']['writes'] if not name.startswith('--')]
    elif r.command == 'verify-db': selected = [r.observed_manifest]+([r.diff_out] if r.diff_out else [])
    elif r.command == 'audit-circular': selected = [r.out_json, r.out_tsv]
    elif r.command == 'run': selected = [Path(path) for path in run_metadata_outputs(r)]
    elif r.command == 'cgc-overlay': selected = [r.corrected_members, r.corrected_summary, r.changes, r.report]
    default_envelope = r.metadata_dir/('envelope.%s.json' % r.command) if r.command in {'validate','summarize','run'} else None
    explicit = getattr(r, 'envelope_out', None)
    if default_envelope is not None and default_envelope not in selected: selected.append(default_envelope)
    if explicit is not None and (default_envelope is None or explicit.resolve() != default_envelope.resolve()): selected.append(explicit)
    w._guard_output_files(selected, files)
    w._guard_output_directories(selected, [])
    for path in selected:
        if path.exists() and not path.is_file():
            raise Refusal('PATHS_OVERLAP', 'A selected output file path is a directory.', details={'path': str(path)})
        parent = path.parent
        while not parent.exists() and parent != parent.parent: parent = parent.parent
        if not parent.is_dir():
            raise Refusal('PATHS_OVERLAP', 'An output parent path is not a directory.', details={'path': str(parent)})
    if explicit is not None and getattr(r, 'results_dir', None):
        w._guard_output_directories([explicit], [r.results_dir])
    if explicit is not None and r.command == 'preflight':
        w._guard_output_directories([explicit], [r.metadata_dir])
    # File guards protect explicitly selected manifests as well as input roots.
    w._guard_output_files([Path(p) for p in paths], files)
    for p in paths:
        w._guard_output_directories([Path(p)], roots)
        for source in files:
            if Path(p).resolve() in source.resolve().parents:
                raise Refusal('PATHS_OVERLAP', 'An output path contains a protected source file.')
    if r.command in {'validate', 'summarize', 'preflight'}:
        w._guard_output_directories([r.metadata_dir], roots)


def observed_artifacts(r, before):
    paths = planned_outputs(r)
    if getattr(r, 'metadata_dir', None) and r.command in {'summarize', 'run'}:
        for p in r.metadata_dir.rglob('*'):
            if p.is_file(): paths.setdefault(str(p.resolve()), 'event_log' if p.name == 'events.jsonl' else 'metadata')
    if r.command == 'run':
        for p in r.results_dir.rglob('*'):
            if p.is_file(): paths.setdefault(str(p.resolve()), 'stage_log' if p.parent.name == 'logs' else 'native_result')
        for status_path in r.metadata_dir.glob('*/stage_status.json'):
            try:
                status = json.loads(status_path.read_text())
                if not isinstance(status, dict): raise ValueError('invalid status document')
            except (OSError, ValueError):
                r._artifact_warnings = [{'code': 'STATUS_UNREADABLE', 'message': WARNINGS_REGISTRY['STATUS_UNREADABLE'], 'location': None}]
                continue
            root = (r.results_dir/status_path.parent.name/'logs').resolve()
            for stage in status.get('stages', {}).values():
                if stage.get('log_file'):
                    log = Path(stage['log_file']).resolve()
                    if root in log.parents: paths.setdefault(str(log), 'stage_log')
    artifacts = []
    for path, role in sorted(paths.items()):
        p = Path(path)
        written = p.is_file() and before.get(path) != (p.stat().st_mtime_ns, p.stat().st_size)
        artifacts.append({'role': role, 'path': path, 'written': written,
                          'sha256': w.sha256_file(p) if written else None})
    return artifacts


def build_envelope(command, cr, policy):
    code = EXIT_CODES[cr.kind]
    if policy == 'semantic-zero' and cr.kind in {'ok', 'negative', 'refused', 'failed'}: code = 0
    diagnostics, total, truncated = bound_diagnostics(cr.diagnostics)
    env = {'contract_version': 1, 'tool': {'name': 'dbcan-workflow', 'version': w.VERSION},
        'command': command, 'run_id': cr.run_id,
        'outcome': {'kind': cr.kind, 'code': cr.code, 'summary': REGISTRY[cr.code]['summary']},
        'exit': {'code': code, 'policy': policy}, 'evidence': cr.evidence,
        'result': sanitize_data(cr.result), 'refusal': cr.refusal, 'findings': cr.findings,
        'warnings': cr.warnings, 'artifacts': cr.artifacts,
        'claims': derive_claims(command, {'kind': cr.kind, 'code': cr.code}, cr.evidence, cr.result),
        'diagnostics': diagnostics, 'diagnostics_total': total, 'diagnostics_truncated': truncated,
        'trust': {'untrusted_paths': list(UNTRUSTED_PATHS)}}
    assert_trusted(env, REGISTRY, WARNINGS_REGISTRY)
    return env


def persist_envelope(env, r, explicit_safe):
    destinations = []
    if explicit_safe and r is not None and env['outcome']['kind'] not in {'refused', 'usage'} and r.command in {'validate', 'summarize', 'run'}:
        destinations.append(r.metadata_dir/('envelope.%s.json' % r.command))
    if explicit_safe and r is not None and getattr(r, 'envelope_out', None): destinations.append(r.envelope_out)
    # Self-hashes are null on disk to avoid circular content hashes. Stdout hashes
    # refer to those exact persisted bytes; the envelope's hash is not evidence.
    for path in dict.fromkeys(p.resolve() for p in destinations):
        artifact = next((a for a in env['artifacts'] if a['path'] == str(path)), None)
        if artifact is None:
            artifact = {'role': 'envelope', 'path': str(path), 'written': True, 'sha256': None}
            env['artifacts'].append(artifact)
        artifact.update(written=True, sha256=None)
    for path in dict.fromkeys(p.resolve() for p in destinations): w.write_json_atomic(path, env)
    for artifact in env['artifacts']:
        if artifact['role'] == 'envelope' and artifact['written']:
            artifact['sha256'] = w.sha256_file(Path(artifact['path']))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    policy = os.environ.get('DBCAN_WORKFLOW_EXIT_POLICY', 'strict')
    # Recover the intended policy even if parsing fails later.
    for i, token in enumerate(argv):
        if token.startswith('--exit-policy='): policy = token.split('=', 1)[1]
        elif token == '--exit-policy' and i+1 < len(argv): policy = argv[i+1]
    r = None; explicit_safe = False; before = {}; command = None
    try:
        if policy not in {'strict', 'semantic-zero'}:
            policy = 'strict'
            raise UsageError('USAGE_INVALID', 'Exit policy must be strict or semantic-zero.')
        parser = w.build_parser()
        choices = parser._subparsers._group_actions[0].choices
        command = next((token for token in argv if token in choices), None)
        r = parser.parse_args(argv)
        command = r.command
        policy = getattr(r, 'exit_policy', policy)
        if command in {'validate', 'summarize'}:
            w.validate_sample_id(r.sample_id if r.sample_id is not None else r.faa.stem)
        if command == 'run':
            if not r.samples or len(set(r.samples)) != len(r.samples):
                raise Refusal('SAMPLE_ID_UNSAFE', 'Sample names must be safe and unique.')
            for sample in r.samples: w.validate_sample_id(sample)
        guard_cli_outputs(r)
        explicit_safe = True
        paths = planned_outputs(r)
        if getattr(r, 'metadata_dir', None) and r.metadata_dir.exists():
            paths.update({str(p.resolve()): 'metadata' for p in r.metadata_dir.rglob('*') if p.is_file()})
        before = {p: (Path(p).stat().st_mtime_ns, Path(p).stat().st_size) for p in paths if Path(p).is_file()}
        for name in ('processed_gff', 'native_members', 'native_summary'):
            path = getattr(r, name, None)
            if path is not None and not path.is_file():
                raise MissingPathRefusal('INPUT_MISSING', 'The selected input file does not exist.', details={'path': str(path)})
        cr = dispatch(r)
        for flag in ('--json', '--tsv'):
            if any(token.split('=', 1)[0] == flag for token in argv):
                cr.warnings.append({'code': 'DEPRECATED_FLAG_'+flag[2:].upper(), 'message': WARNINGS_REGISTRY['DEPRECATED_FLAG_'+flag[2:].upper()], 'location': None})
    except WorkflowOutcome as exc:
        cr = CommandResult.from_exception(exc)
        if cr.refusal is not None and r is not None:
            names = ('faa', 'gff', 'input_dir', 'results_dir', 'metadata_dir', 'db_dir',
                'env_dir', 'expected_manifest', 'observed_manifest', 'status_file', 'threads',
                'profile', 'allow_unattested', 'sample_id', 'samples')
            details = {key: str(getattr(r,key)) if isinstance(getattr(r,key),Path) else getattr(r,key)
                       for key in names if hasattr(r,key)}
            if exc.code == 'SAMPLE_ID_UNSAFE':
                details.pop('sample_id',None);details.pop('samples',None)
            cr.refusal['details'].update(bounded_details(details, max_items=32))
            if 'samples' in details:
                cr.refusal['details']['samples'] = bounded_details(details['samples'])
    except Exception:
        traceback.print_exc(file=sys.stderr)
        cr = CommandResult(kind='error', code='INTERNAL_ERROR', summary=REGISTRY['INTERNAL_ERROR']['summary'])
    try:
        if r is not None:
            if cr.kind in {'refused', 'usage'}:
                cr.artifacts = [{'role': role, 'path': path, 'written': False, 'sha256': None} for path,role in sorted(planned_outputs(r).items())]
            else: cr.artifacts = observed_artifacts(r, before)
            cr.warnings.extend(getattr(r, '_artifact_warnings', []))
        env = build_envelope(command, cr, policy)
        json.dumps(env, allow_nan=False)  # Reject invalid values before persistence.
    except Exception:
        traceback.print_exc(file=sys.stderr)
        cr = CommandResult(kind='error', code='INTERNAL_ERROR', summary=REGISTRY['INTERNAL_ERROR']['summary'])
        env = build_envelope(command, cr, policy)
        explicit_safe = False
    try:
        persist_envelope(env, r, explicit_safe)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        env['warnings'].append({'code': 'ENVELOPE_PERSIST_FAILED', 'message': WARNINGS_REGISTRY['ENVELOPE_PERSIST_FAILED'], 'location': None})
        for artifact in env['artifacts']:
            if artifact['role'] == 'envelope': artifact.update(written=False, sha256=None)
    try:
        payload = json.dumps(env, indent=2, sort_keys=True, allow_nan=False) + '\n'
    except (ValueError, TypeError):
        traceback.print_exc(file=sys.stderr)
        env = build_envelope(command, CommandResult(kind='error', code='INTERNAL_ERROR', summary=REGISTRY['INTERNAL_ERROR']['summary']), policy)
        payload = json.dumps(env, indent=2, sort_keys=True, allow_nan=False) + '\n'
    sys.stdout.write(payload)
    return env['exit']['code']


def describe_commands():
    parser = w.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) == set(w.COMMAND_METADATA)
    commands = {}
    for name, subparser in choices.items():
        arguments = []
        for action in subparser._actions:
            if action.dest == 'help': continue
            arguments.append({'flags': action.option_strings, 'required': action.required,
                'help': action.help, 'choices': list(action.choices) if action.choices is not None else None,
                'default': None if action.default == argparse.SUPPRESS else action.default,
                'nargs': action.nargs})
        codes = ['OK', 'USAGE_INVALID', 'PATHS_OVERLAP', 'INTERNAL_ERROR']
        if name not in {'describe', 'verify-db'}: codes += ['INPUT_MISSING', 'STRUCTURE_INVALID']
        if name in {'prepare', 'validate', 'summarize'}: codes += ['INPUT_MISMATCH']
        if name in {'validate', 'summarize'}: codes += ['RESULTS_DIR_MISSING', 'INPUT_MISMATCH', 'SAMPLE_ID_UNSAFE']
        if name == 'cgc-overlay': codes += ['VERSION_UNSUPPORTED']
        if name == 'validate': codes += ['ATTESTATION_REQUIRED', 'ATTESTATION_REJECTED']
        if name in {'verify-db', 'preflight', 'run'}: codes += ['MANIFEST_PATH_UNSAFE']
        if name == 'verify-db': codes += ['DB_MISMATCH', 'DB_UNVERIFIED', 'INPUT_MISSING']
        if name in {'preflight', 'run'}: codes += ['ENV_UNMET', 'DB_UNVERIFIED', 'THREADS_EXCEED_ALLOCATION', 'INPUT_MISMATCH']
        if name == 'run': codes += ['SAMPLE_ID_UNSAFE', 'STAGE_FAILED']
        if name == 'preflight': codes = ['OK', 'USAGE_INVALID', 'PATHS_OVERLAP', 'PREFLIGHT_UNMET', 'INTERNAL_ERROR']
        commands[name] = {**w.COMMAND_METADATA[name], 'args': arguments,
            'writes': w.COMMAND_METADATA[name]['writes']+['--envelope-out (optional)'],
            'reads_db': name in {'verify-db','preflight','run'}, 'requires_user_confirmation': name=='run',
            'needs_network': False, 'outcome_codes': sorted(set(codes))}
    return {'commands': commands, 'exit_codes': EXIT_CODES,
        'database_stage_assets': {k: list(v) for k,v in w.DB_ASSETS_BY_STAGE.items()}}


def commands_markdown(description):
    rows = ['| Command | Purpose | Writes |', '|---|---|---|']
    for name, meta in description['commands'].items():
        rows.append('| `%s` | %s | %s |' % (name, meta['summary'], ', '.join(meta['writes'])))
    rows += ['', 'Required database assets for a new search:']
    for stage, assets in description['database_stage_assets'].items():
        rows.append('- `%s`: %s.' % (stage, ', '.join('`%s`' % a for a in assets) or 'none'))
    return '\n'.join(rows)
