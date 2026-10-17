"""CLI adapters; library dictionaries remain compatible with v0.2.0 callers."""
from __future__ import annotations
import json
from pathlib import Path
import dbcan_workflow as w
from dbcan_outcomes import CommandResult, Refusal


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
        w.write_json_atomic(metadata / 'output_validation.json', data)
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

# The stdout contract is emitted once, after execution and guarded persistence.
import argparse
import os
import sys
import traceback
from dbcan_outcomes import EXIT_CODES, REGISTRY, WorkflowOutcome, UsageError


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
    if r.command in {'validate', 'summarize', 'run'}:
        add(r.metadata_dir/('envelope.%s.json' % r.command), 'envelope')
    add(getattr(r, 'envelope_out', None), 'envelope')
    return outputs


def protected_paths(r):
    roots = [getattr(r, key) for key in ('input_dir', 'db_dir', 'env_dir') if getattr(r, key, None)]
    if r.command != 'run' and getattr(r, 'results_dir', None): roots.append(r.results_dir)
    roots += [getattr(r, key).resolve().parent for key in ('faa', 'gff') if getattr(r, key, None)]
    files = [getattr(r, key) for key in ('faa', 'gff', 'expected_manifest', 'status_file') if getattr(r, key, None)]
    return roots, files


def guard_cli_outputs(r):
    roots, files = protected_paths(r)
    paths = planned_outputs(r)
    if r.command == 'verify-db' and r.diff_out:
        w._guard_output_files([r.diff_out, r.observed_manifest], files)
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
            if p.is_file(): paths.setdefault(str(p.resolve()), 'metadata')
    if r.command == 'run':
        for p in r.results_dir.rglob('*'):
            if p.is_file(): paths.setdefault(str(p.resolve()), 'stage_log' if 'logs' in p.parts else 'native_result')
    artifacts = []
    for path, role in sorted(paths.items()):
        p = Path(path)
        written = p.is_file() and before.get(path) != (p.stat().st_mtime_ns, p.stat().st_size)
        artifacts.append({'role': role, 'path': path, 'written': written,
                          'sha256': w.sha256_file(p) if written else None})
    return artifacts


from dbcan_claims import derive_claims


def build_envelope(command, cr, policy):
    code = EXIT_CODES[cr.kind]
    if policy == 'semantic-zero' and cr.kind in {'ok', 'negative', 'refused', 'failed'}: code = 0
    return {'contract_version': 1, 'tool': {'name': 'dbcan-workflow', 'version': w.VERSION},
        'command': command, 'run_id': cr.run_id,
        'outcome': {'kind': cr.kind, 'code': cr.code, 'summary': cr.summary},
        'exit': {'code': code, 'policy': policy}, 'evidence': cr.evidence,
        'result': cr.result, 'refusal': cr.refusal, 'findings': cr.findings,
        'warnings': cr.warnings, 'artifacts': cr.artifacts,
        'claims': derive_claims(command, {'kind': cr.kind, 'code': cr.code}, cr.evidence, cr.result)}


def persist_envelope(env, r, explicit_safe):
    destinations = []
    if r is not None and env['outcome']['kind'] not in {'refused', 'usage'} and r.command in {'validate', 'summarize', 'run'}:
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
    r = None; explicit_safe = False; before = {}; command = 'describe'
    try:
        if policy not in {'strict', 'semantic-zero'}:
            policy = 'strict'
            raise UsageError('USAGE_INVALID', 'Exit policy must be strict or semantic-zero.')
        parser = w.build_parser()
        choices = parser._subparsers._group_actions[0].choices
        command = next((token for token in argv if token in choices), 'describe')
        r = parser.parse_args(argv)
        command = r.command
        policy = getattr(r, 'exit_policy', policy)
        guard_cli_outputs(r)
        explicit_safe = True
        paths = planned_outputs(r)
        if getattr(r, 'metadata_dir', None) and r.metadata_dir.exists():
            paths.update({str(p.resolve()): 'metadata' for p in r.metadata_dir.rglob('*') if p.is_file()})
        before = {p: (Path(p).stat().st_mtime_ns, Path(p).stat().st_size) for p in paths if Path(p).is_file()}
        cr = dispatch(r)
    except WorkflowOutcome as exc:
        cr = CommandResult.from_exception(exc)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        cr = CommandResult(kind='error', code='INTERNAL_ERROR', summary=REGISTRY['INTERNAL_ERROR']['summary'])
    try:
        if r is not None: cr.artifacts = observed_artifacts(r, before)
        env = build_envelope(command, cr, policy)
        persist_envelope(env, r, explicit_safe)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        cr = CommandResult(kind='error', code='INTERNAL_ERROR', summary='Envelope persistence failed; report the stderr traceback.')
        env = build_envelope(command, cr, policy)
    sys.stdout.write(json.dumps(env, indent=2, sort_keys=True, allow_nan=False) + '\n')
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
                'default': None if action.default is argparse.SUPPRESS else action.default,
                'nargs': action.nargs})
        codes = ['OK', 'USAGE_INVALID', 'PATHS_OVERLAP', 'INTERNAL_ERROR']
        if name not in {'describe', 'verify-db'}: codes += ['INPUT_MISSING', 'STRUCTURE_INVALID']
        if name in {'validate', 'summarize'}: codes += ['RESULTS_DIR_MISSING', 'INPUT_MISMATCH']
        if name == 'validate': codes += ['ATTESTATION_REQUIRED', 'ATTESTATION_REJECTED']
        if name in {'verify-db', 'preflight', 'run'}: codes += ['MANIFEST_PATH_UNSAFE']
        if name == 'verify-db': codes += ['DB_MISMATCH']
        if name in {'preflight', 'run'}: codes += ['ENV_UNMET', 'DB_UNVERIFIED', 'THREADS_EXCEED_ALLOCATION', 'INPUT_MISMATCH']
        if name == 'run': codes += ['SAMPLE_ID_UNSAFE', 'STAGE_FAILED']
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
