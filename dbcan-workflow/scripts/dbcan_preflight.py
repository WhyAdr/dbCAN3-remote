"""Independent readiness checks with a strict execution gate."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from dbcan_outcomes import (WorkflowOutcome, Refusal, RuntimeRefusal,
                            MissingPathRefusal)


class PreflightReport(dict):
    """JSON-compatible report; original typed exceptions stay private to Python."""
    def __init__(self):
        super().__init__(checks=[])
        self.blockers = []


def require_preflight(report):
    """A true readiness flag never overrides a failed, skipped or absent check."""
    checks = report.get('checks', [])
    if report.get('ready') is True and checks and all(row['state']=='pass' for row in checks):
        return
    blockers = getattr(report, 'blockers', [])
    exc = blockers[0] if blockers else Refusal('ENV_UNMET', 'Every required preflight check must pass before execution.')
    exc.preflight_report = dict(report)
    raise exc


def collect_preflight(faa, gff, env_python, run_dbcan_path, diamond_path,
                      db_dir, expected_manifest, threads, profile, results_dir, metadata_dir, *, stop_on_failure=False):
    import dbcan_workflow as w

    # An unsafe layout is a hard boundary, not a diagnostic probe target.
    w._guard_output_directories([results_dir, metadata_dir],
        [faa.parent, gff.parent, db_dir, env_python.parent.parent, expected_manifest])
    report = PreflightReport()
    report.update(profile=profile, threads=threads)
    states = {}
    values = {}

    def check(id, function, *, needs=(), io_code='ENV_UNMET'):
        blocked = [key for key in needs if states[key] != 'pass']
        if blocked:
            states[id] = 'skipped'
            report['checks'].append({'id': id, 'state': 'skipped', 'detail': {'blocked_by': blocked}})
            return None
        try:
            value = function()
        except WorkflowOutcome as exc:
            states[id] = 'fail'
            report.blockers.append(exc)
            report['checks'].append({'id': id, 'state': 'fail',
                'detail': {'code': exc.code, 'message': str(exc), 'parameters': exc.details}})
            if stop_on_failure:
                report.update(ready=False, preflight_status='unmet')
                exc.preflight_report = dict(report)
                raise
            return None
        except OSError as cause:
            exc = Refusal(io_code, 'A required preflight resource could not be read.', details={'check_id': id})
            exc.__cause__ = cause
            states[id] = 'fail'
            report.blockers.append(exc)
            report['checks'].append({'id': id, 'state': 'fail',
                'detail': {'code': exc.code, 'message': str(exc)}})
            if stop_on_failure:
                report.update(ready=False, preflight_status='unmet')
                exc.preflight_report = dict(report)
                raise exc from cause
            return None
        states[id] = 'pass'
        values[id] = value
        report['checks'].append({'id': id, 'state': 'pass', 'detail': {'message': 'Check passed.'}})
        return value

    check('output_paths', lambda: True)

    def fresh_destinations():
        for path in (results_dir, metadata_dir):
            if path.exists() and (not path.is_dir() or any(path.iterdir())):
                raise Refusal('PATHS_OVERLAP', 'Run destinations must be fresh and empty.', details={'path': str(path)})
    check('destinations_fresh', fresh_destinations)

    def thread_budget():
        if type(threads) is not int or threads < 1:
            raise Refusal('ENV_UNMET', 'threads must be a positive integer')
    check('thread_budget', thread_budget)

    def resource_profile():
        if profile not in {'sandbox', 'hpc'}:
            raise Refusal('ENV_UNMET', 'profile must be sandbox or hpc')
    check('resource_profile', resource_profile)
    paired = check('input_pair', lambda: w.compare_faa_gff(faa, gff), io_code='INPUT_MISSING')
    if paired is not None:
        report.update(protein_count=len(paired['proteins']), contig_count=len(paired['annotation']['seq_regions']))
    resources = check('resource_allocation', w.effective_resources)
    report['resources'] = resources if resources is not None else {}

    def cpu_budget():
        allocation = resources['effective_cpu_allocation']
        if not allocation:
            raise Refusal('ENV_UNMET', 'The effective CPU allocation could not be established.')
        if threads > allocation:
            raise Refusal('THREADS_EXCEED_ALLOCATION',
                f'requested threads={threads} exceeds detected CPU allocation {allocation}')
    check('cpu_budget', cpu_budget, needs=('thread_budget', 'resource_allocation'))

    paths = [Path(os.path.abspath(path)) for path in (env_python, run_dbcan_path, diamond_path)]
    env_root = paths[0].parent.parent.resolve()
    labels = [('python_executable', 'Python', paths[0]),
              ('run_dbcan_executable', 'run_dbcan', paths[1]),
              ('diamond_executable', 'DIAMOND', paths[2])]
    for id, label, path in labels:
        def executable(path=path, label=label):
            if not path.is_file() or not os.access(path, os.X_OK):
                raise MissingPathRefusal('ENV_UNMET', f'selected {label} executable is not executable: {path}')
        check(id, executable)

    def layout():
        if any(path.parent.resolve() != env_root/'bin' for path in paths):
            raise Refusal('ENV_UNMET', 'Python, run_dbcan, and DIAMOND must be selected from one environment bin directory')
    check('environment_layout', layout)
    env = os.environ.copy()
    env['PATH'] = str(env_root/'bin')+os.pathsep+env.get('PATH', '')

    def probe(argv):
        try:
            return subprocess.run(argv, check=False, capture_output=True, text=True, env=env)
        except OSError as exc:
            raise RuntimeRefusal('ENV_UNMET', 'A selected runtime probe could not start.',
                details={'executable': str(argv[0])}) from exc

    def python_probe():
        result = probe([str(paths[0]), '-c',
            "import platform,sys,json,importlib.metadata; "
            "print(json.dumps({'python':sys.version.split()[0],'machine':platform.machine(),"
            "'prefix':sys.prefix,'dbcan':importlib.metadata.version('dbcan'),"
            "'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata['Name']}}))"])
        if result.returncode != 0:
            raise RuntimeRefusal('ENV_UNMET', 'The selected Python smoke test failed.')
        try:
            runtime = json.loads(result.stdout)
            if not isinstance(runtime, dict) or any(not isinstance(runtime.get(key), str)
                for key in ('python', 'machine', 'prefix', 'dbcan')) or not isinstance(runtime.get('packages'), dict):
                raise ValueError('invalid runtime fields')
        except ValueError as exc:
            raise RuntimeRefusal('ENV_UNMET', 'The selected Python probe returned malformed runtime metadata.') from exc
        return runtime
    runtime = check('python_probe', python_probe, needs=('python_executable', 'environment_layout'))

    def identity():
        if Path(runtime['prefix']).resolve() != env_root or runtime['dbcan'] != w.DBCAN_VERSION:
            raise Refusal('ENV_UNMET', 'selected Python environment identity or dbcan distribution version differs from the requested environment')
        report.update(python=str(paths[0]), python_version=runtime['python'], machine=runtime['machine'],
            python_prefix=runtime['prefix'], resolved_package_versions=runtime['packages'])
    check('python_identity', identity, needs=('python_probe',))

    def version(argv, expected, label, key):
        result = probe(argv)
        output = result.stdout + result.stderr
        if result.returncode != 0 or not re.search(r'(?<!\d)'+re.escape(expected)+r'(?!\d)', output):
            raise RuntimeRefusal('ENV_UNMET', f'The {label} version probe failed or was not {expected}.')
        report[key] = str(paths[1] if key=='run_dbcan' else paths[2])
        report[key+'_version_output'] = output.strip()
    check('run_dbcan_version', lambda: version([str(paths[0]), str(paths[1]), 'version'], w.DBCAN_VERSION, 'run_dbcan', 'run_dbcan'),
        needs=('python_identity', 'run_dbcan_executable'))
    check('diamond_version', lambda: version([str(paths[2]), 'version'], '2.2.8', 'DIAMOND', 'diamond'),
        needs=('diamond_executable', 'environment_layout'))

    def executable_hashes():
        report['executable_observed_sha256'] = {str(path): w.sha256_file(path) for path in paths}
    check('executable_hashes', executable_hashes, needs=tuple(id for id, _, _ in labels))

    def storage():
        disk = {}
        for path in (results_dir, metadata_dir, db_dir):
            parent = path.resolve()
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            disk[str(path.resolve())] = shutil.disk_usage(parent).free
        report['resources']['disk_free_bytes_by_path'] = disk
    check('storage_snapshot', storage)

    # The same strict database inspector used by library callers remains the
    # authority. On refusal, inspect independent asset/manifest axes separately.
    database_error = None
    try:
        database = w.db_preflight(db_dir, expected_manifest, w.STAGE_NAMES)
    except WorkflowOutcome as exc:
        database_error = exc
        database = None
    except OSError as cause:
        database_error = Refusal('DB_UNVERIFIED', 'The database cache could not be read.')
        database_error.__cause__ = cause
        database = None
    if stop_on_failure and database_error is not None:
        def refuse_database():
            raise database_error
        check('database_assets' if 'missing_by_stage' in database_error.details else 'database_manifest', refuse_database)
    if database is not None:
        check('database_assets', lambda: database)
        check('database_manifest', lambda: database)
        report['database'] = database
    else:
        database = {'asset_checks': {}}
        def assets():
            missing_by_stage = {}
            for stage, names in w.DB_ASSETS_BY_STAGE.items():
                missing = [name for name in names if not ((db_dir/name).is_dir() if name=='dbCAN-PUL' else (db_dir/name).is_file())]
                database['asset_checks'][stage] = {'required': list(names), 'missing': missing, 'ready': not missing}
                if missing: missing_by_stage[stage] = missing
            if missing_by_stage:
                raise MissingPathRefusal('DB_UNVERIFIED', 'Required database stage assets are missing.',
                    details={'db_dir': str(db_dir), 'missing_by_stage': missing_by_stage})
        check('database_assets', assets, io_code='DB_UNVERIFIED')

        def manifest():
            observed = getattr(database_error, 'manifest_check', None)
            if observed is None:
                observed = w.verify_database(db_dir, expected_manifest)
            bounded = dict(observed)
            for key in ('missing', 'unexpected', 'mismatched'):
                bounded[key+'_count'] = len(observed[key])
                bounded[key] = observed[key][:20]
            bounded['listed_truncated'] = any(len(observed[key])>20 for key in ('missing', 'unexpected', 'mismatched'))
            database['manifest_check'] = bounded
            if not observed['match']:
                raise Refusal('DB_UNVERIFIED', 'The database cache does not match the preserved manifest.',
                    details={key+'_count': len(observed[key]) for key in ('missing', 'unexpected', 'mismatched')})
        check('database_manifest', manifest, io_code='DB_UNVERIFIED')
        report['database'] = database
    report['ready'] = bool(report['checks']) and all(row['state']=='pass' for row in report['checks'])
    report['preflight_status'] = 'passed' if report['ready'] else 'unmet'
    return report
