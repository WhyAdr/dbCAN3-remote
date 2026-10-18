"""Phase-four diagnostics with controlled subprocesses and synthetic inputs."""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import dbcan_workflow as w
import dbcan_cli as cli
from dbcan_events import append_event, failure_context, LOG_TAIL_BYTES, LOG_TAIL_LINES
from dbcan_outcomes import Refusal
from test_contract import check_envelope


class Phase4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = ROOT/'tests/fixtures/zero_hit'
        self.inputs = self.root/'inputs/original'
        self.inputs.mkdir(parents=True)
        for sample in ('alpha', 'beta'):
            for suffix in ('faa', 'gff3'):
                shutil.copy2(self.fixture/('inputs/sample.'+suffix), self.inputs/(sample+'.'+suffix))
        self.results = self.root/'results'
        self.metadata = self.root/'metadata'
        self.manifest = self.root/'expected.sha256'
        self.manifest.write_text('synthetic preflight fixture\n')
        self.preflight = {'database': {'manifest_check': {'snapshot': 'synthetic_fixture'}}}

    def commands(self, failure_sample=None):
        def build(run_dbcan, faa, local_gff, results, db, threads, logs, **kwargs):
            seed = 'import shutil; shutil.copytree(%r, %r, dirs_exist_ok=True)' % (str(self.fixture/'results'), str(results))
            commands = []
            for i, name in enumerate(w.STAGE_NAMES):
                source = seed if i == 0 else 'pass'
                if i == 1 and faa.stem == failure_sample:
                    source = "import sys; print(('failure-line-'+'x'*300+'\\n')*100); sys.exit(7)"
                commands.append((name, [sys.executable, '-c', source], logs/(name+'.log')))
            return commands
        return build

    def run_batch(self, failure_sample=None):
        with patch.object(w, 'run_preflight', return_value=self.preflight), patch.object(w, 'stage_commands', side_effect=self.commands(failure_sample)):
            return w.run_workflow(self.inputs.parent, self.results, self.metadata, self.root/'db',
                self.manifest, self.root/'env', ['alpha', 'beta'], 1, 'sandbox')

    def events(self, sample):
        return [json.loads(line) for line in (self.metadata/sample/'events.jsonl').read_text().splitlines()]

    def test_success_events_are_separate_per_sample_and_do_not_change_attestation(self):
        result = self.run_batch()
        self.assertEqual(result['status'], 'complete')
        for sample in ('alpha', 'beta'):
            records = self.events(sample)
            self.assertTrue(all(set(('ts', 'run_id', 'sample', 'stage', 'event')) <= set(row) for row in records))
            self.assertTrue(all(row['sample'] == sample and row['run_id'] == result['run_id'] for row in records))
            expected = ['run_started']
            for _ in w.STAGE_NAMES: expected += ['stage_started', 'stage_succeeded']
            expected += ['validation_started', 'validation_succeeded', 'run_succeeded']
            self.assertEqual([row['event'] for row in records], expected)
            self.assertEqual([row['stage'] for row in records if row['event']=='stage_started'], list(w.STAGE_NAMES))
            before = w._hash_tree(self.results/sample)
            append_event(self.metadata/sample/'events.jsonl', result['run_id'], sample, None, 'review_note')
            self.assertEqual(before, w._hash_tree(self.results/sample))
            validation = w.validate_outputs(self.inputs/(sample+'.faa'), self.inputs/(sample+'.gff3'), self.results/sample,
                status_file=self.metadata/sample/'stage_status.json')
            self.assertTrue(validation['execution_attested'])
            self.assertFalse((self.results/sample/'events.jsonl').exists())

    def test_failed_sample_keeps_context_and_other_sample_continues(self):
        result = self.run_batch('alpha')
        self.assertEqual(result['status'], 'failed')
        failure = result['failures'][0]
        self.assertEqual(failure['sample'], 'alpha')
        self.assertEqual(failure['stage'], 'gff_process')
        self.assertEqual(failure['exit_code'], 7)
        self.assertTrue(failure['log_tail_truncated'])
        self.assertLessEqual(len(failure['log_tail'].encode()), LOG_TAIL_BYTES)
        self.assertLessEqual(len(failure['log_tail'].splitlines()), LOG_TAIL_LINES)
        self.assertIn('/results/alpha/logs/', failure['log_path'])
        status = json.loads((self.metadata/'alpha/stage_status.json').read_text())
        self.assertEqual(status['failure']['log_tail'], failure['log_tail'])
        events = [row['event'] for row in self.events('alpha')]
        self.assertEqual(events.count('stage_failed'), 1)
        self.assertEqual(events.count('stage_skipped'), 2)
        self.assertEqual(events[-1], 'run_failed')
        self.assertNotIn('run_succeeded', events)
        self.assertFalse((self.metadata/'alpha/completion.json').exists())
        self.assertEqual(self.events('beta')[-1]['event'], 'run_succeeded')

    def test_append_is_not_rewrite_and_refused_roots_do_not_append(self):
        path = self.root/'events.jsonl'
        append_event(path, 'id', 'alpha', None, 'first')
        prefix = path.read_bytes()
        append_event(path, 'id', 'alpha', None, 'second')
        self.assertTrue(path.read_bytes().startswith(prefix))
        self.metadata.mkdir()
        stale = self.metadata/'events.jsonl'; stale.write_bytes(prefix)
        with self.assertRaises(Refusal): self.run_batch()
        self.assertEqual(stale.read_bytes(), prefix)
        self.assertFalse(self.results.exists())

    def test_tail_is_bounded_for_long_lines_unicode_and_missing_files(self):
        for payload in (b'x'*40000, ('\u03bb'*40000).encode(), b'\xff'*40000, b'a\n'*200):
            path = self.root/'log'; path.write_bytes(payload)
            context = failure_context('alpha', 'stage', 7, path)
            self.assertLessEqual(len(context['log_tail'].encode()), LOG_TAIL_BYTES)
            self.assertLessEqual(len(context['log_tail'].splitlines()), LOG_TAIL_LINES)
            self.assertTrue(context['log_tail_truncated'])
        missing = failure_context('alpha', 'stage', None, self.root/'missing')
        self.assertEqual(missing['log_tail'], '')
        self.assertIn('log_tail_error', missing)

    def test_stage_cannot_start_still_records_one_failure(self):
        def commands(*args, **kwargs):
            return [(name, [str(self.root/'missing-executable')], args[6]/(name+'.log')) for name in w.STAGE_NAMES]
        with patch.object(w, 'run_preflight', return_value=self.preflight), patch.object(w, 'stage_commands', side_effect=commands):
            result = w.run_workflow(self.inputs.parent, self.results, self.metadata, self.root/'db',
                self.manifest, self.root/'env', ['alpha'], 1, 'sandbox')
        self.assertIsNone(result['failures'][0]['exit_code'])
        self.assertEqual([r['event'] for r in self.events('alpha')].count('stage_failed'), 1)

    def test_cli_failure_indexes_events_and_preserves_log_location(self):
        args = ['run', '--input-dir', str(self.inputs.parent), '--results-dir', str(self.results), '--metadata-dir', str(self.metadata),
            '--db-dir', str(self.root/'db'), '--env-dir', str(self.root/'env'), '--expected-manifest', str(self.manifest),
            '--samples', 'alpha', '--threads', '1', '--profile', 'sandbox']
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(w, 'run_preflight', return_value=self.preflight), patch.object(w, 'stage_commands', side_effect=self.commands('alpha')), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(args)
        envelope = json.loads(stdout.getvalue()); check_envelope(self, envelope)
        self.assertEqual(code, 5)
        self.assertIn('log_tail', envelope['result']['failures'][0])
        self.assertTrue(any(a['role']=='event_log' and a['written'] for a in envelope['artifacts']))
        self.assertTrue(any(a['role']=='stage_log' and '/results/alpha/logs/' in a['path'] for a in envelope['artifacts']))
        self.assertNotIn('Traceback', stderr.getvalue())

    def ready_environment(self):
        self.env = self.root/'env'
        (self.env/'bin').mkdir(parents=True)
        for name in ('python', 'run_dbcan', 'diamond'):
            path = self.env/'bin'/name
            path.write_text('#!/bin/sh\nexit 0\n'); path.chmod(0o755)
        self.db = self.root/'db'; self.db.mkdir()
        for names in w.DB_ASSETS_BY_STAGE.values():
            for name in names:
                path = self.db/name
                if name == 'dbCAN-PUL':
                    path.mkdir(exist_ok=True); (path/'synthetic').write_text('fixture')
                else: path.write_text(name)
        files = [p for p in sorted(self.db.rglob('*')) if p.is_file()]
        self.manifest.write_text(''.join(w.sha256_file(p)+'  ./'+p.relative_to(self.db).as_posix()+'\n' for p in files))

    def runtime_probe(self, argv, **kwargs):
        if '-c' in argv:
            output = json.dumps({'python': '3.12.0', 'machine': 'x86_64', 'prefix': str(self.env), 'dbcan': '5.2.9', 'packages': {}})
        elif Path(argv[0]).name == 'diamond': output = 'diamond 2.2.8'
        else: output = 'dbCAN 5.2.9'
        return subprocess.CompletedProcess(argv, 0, output, '')

    def collect(self, threads=1):
        return w.collect_preflight(self.inputs/'alpha.faa', self.inputs/'alpha.gff3', self.env/'bin/python', self.env/'bin/run_dbcan',
            self.env/'bin/diamond', self.db, self.manifest, threads, 'sandbox', self.results, self.metadata)

    def test_preflight_collects_independent_failures_and_skips_dependencies(self):
        self.ready_environment()
        (self.env/'bin/diamond').unlink()
        (self.db/'CAZy.dmnd').unlink()
        path = self.inputs/'alpha.gff3'; path.write_text(path.read_text().replace('ID=p1', 'ID=other'))
        before = w._hash_tree(self.root)
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe), patch.object(w, 'effective_resources', return_value={'effective_cpu_allocation': 1}):
            report = self.collect(threads=2)
        self.assertFalse(report['ready'])
        checks = {row['id']: row for row in report['checks']}
        for id in ('input_pair', 'cpu_budget', 'diamond_executable', 'database_assets', 'database_manifest'):
            self.assertEqual(checks[id]['state'], 'fail', id)
        for id in ('python_probe', 'python_identity', 'run_dbcan_version', 'storage_snapshot'):
            self.assertEqual(checks[id]['state'], 'pass', id)
        self.assertEqual(checks['diamond_version']['detail']['blocked_by'], ['diamond_executable'])
        self.assertEqual(checks['diamond_version']['state'], 'skipped')
        self.assertEqual(checks['executable_hashes']['state'], 'skipped')
        self.assertEqual(report['database']['manifest_check']['missing_count'], 1)
        self.assertEqual(before, w._hash_tree(self.root))
        self.assertFalse(self.results.exists()); self.assertFalse(self.metadata.exists())
        json.dumps(report)  # Private original exceptions must not leak into JSON.

    def test_complete_preflight_and_strict_facade_keep_provenance(self):
        self.ready_environment()
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe):
            report = w.run_preflight(self.inputs/'alpha.faa', self.inputs/'alpha.gff3', self.env/'bin/python', self.env/'bin/run_dbcan',
                self.env/'bin/diamond', self.db, self.manifest, 1, 'sandbox', self.results, self.metadata)
        self.assertTrue(report['ready'])
        self.assertTrue(all(row['state']=='pass' for row in report['checks']))
        self.assertEqual(report['python'], str(self.env/'bin/python'))
        self.assertEqual(report['python_prefix'], str(self.env))
        self.assertEqual(report['preflight_status'], 'passed')
        self.assertTrue(report['database']['manifest_check']['match'])
        self.assertEqual(report['protein_count'], 1)
        self.assertEqual(len(report['checks']), len({row['id'] for row in report['checks']}))

    def test_safety_overlap_stops_before_probes_or_database_reads(self):
        self.ready_environment()
        with patch.object(w.subprocess, 'run') as probe, patch.object(w, 'db_preflight') as database:
            with self.assertRaises(Refusal) as caught:
                w.collect_preflight(self.inputs/'alpha.faa', self.inputs/'alpha.gff3', self.env/'bin/python', self.env/'bin/run_dbcan',
                    self.env/'bin/diamond', self.db, self.manifest, 1, 'sandbox', self.inputs/'derived', self.metadata)
        self.assertEqual(caught.exception.code, 'PATHS_OVERLAP')
        probe.assert_not_called(); database.assert_not_called()
        self.assertFalse((self.inputs/'derived').exists())

    def test_readiness_boolean_cannot_override_failed_or_skipped_checks(self):
        from dbcan_preflight import require_preflight
        for state in ('fail', 'skipped'):
            with self.assertRaises(Refusal):
                require_preflight({'ready': True, 'checks': [{'id': 'critical', 'state': state, 'detail': {}}]})
        with self.assertRaises(Refusal): require_preflight({'ready': True, 'checks': []})

    def test_failed_manifest_is_hashed_once_for_diagnostic_report(self):
        self.ready_environment()
        (self.db/'CAZy.dmnd').write_text('corrupted')
        verify = w.verify_database
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe), patch.object(w, 'verify_database', wraps=verify) as verification:
            report = self.collect()
        self.assertFalse(report['ready'])
        verification.assert_called_once()
        checks = {row['id']: row['state'] for row in report['checks']}
        self.assertEqual(checks['database_assets'], 'pass')
        self.assertEqual(checks['database_manifest'], 'fail')

    def test_unexpected_probe_defects_are_not_converted_to_unmet_requirements(self):
        self.ready_environment()
        with patch.object(w.subprocess, 'run', side_effect=RuntimeError('synthetic defect')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic defect'): self.collect()

    def preflight_args(self):
        return ['preflight', '--faa', str(self.inputs/'alpha.faa'), '--gff', str(self.inputs/'alpha.gff3'),
            '--env-dir', str(self.env), '--db-dir', str(self.db), '--expected-manifest', str(self.manifest),
            '--threads', '1', '--profile', 'sandbox', '--results-dir', str(self.results), '--metadata-dir', str(self.metadata)]

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr): code = cli.main(args)
        data = json.loads(stdout.getvalue()); check_envelope(self, data)
        self.assertEqual(code, data['exit']['code'])
        return data, stderr.getvalue()

    def test_cli_preflight_unmet_reports_checks_under_both_exit_policies(self):
        self.ready_environment(); (self.env/'bin/diamond').unlink()
        before = w._hash_tree(self.root)
        for policy, exit_code in [('strict', 4), ('semantic-zero', 0)]:
            with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe):
                data, stderr = self.invoke(self.preflight_args()+['--exit-policy', policy])
            self.assertEqual(data['outcome']['code'], 'PREFLIGHT_UNMET')
            self.assertEqual(data['outcome']['kind'], 'negative')
            self.assertEqual(data['exit']['code'], exit_code)
            self.assertIsNone(data['refusal'])
            self.assertEqual(data['evidence']['structure'], 'not_assessed')
            self.assertTrue(data['findings'])
            self.assertIn('CL-N1', [claim['id'] for claim in data['claims']['may_not_say']])
            self.assertNotIn('CL-N0', [claim['id'] for claim in data['claims']['may_not_say']])
            self.assertEqual(before, w._hash_tree(self.root))
            self.assertFalse(self.results.exists()); self.assertFalse(self.metadata.exists())
            self.assertNotIn('Traceback', stderr)

    def test_cli_preflight_report_can_be_persisted_explicitly(self):
        self.ready_environment(); (self.env/'bin/diamond').unlink()
        output = self.root/'diagnostics/preflight.json'
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe):
            data, _ = self.invoke(self.preflight_args()+['--envelope-out', str(output)])
        self.assertEqual(data['outcome']['code'], 'PREFLIGHT_UNMET')
        self.assertEqual(json.loads(output.read_text())['result']['checks'], data['result']['checks'])
        self.assertFalse(self.metadata.exists()); self.assertFalse(self.results.exists())

    def test_run_refuses_failed_preflight_without_creating_results_or_events(self):
        self.ready_environment(); (self.env/'bin/diamond').unlink()
        args = ['run', '--input-dir', str(self.inputs.parent), '--results-dir', str(self.results), '--metadata-dir', str(self.metadata),
            '--env-dir', str(self.env), '--db-dir', str(self.db), '--expected-manifest', str(self.manifest), '--samples', 'alpha', '--threads', '1', '--profile', 'sandbox']
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe), patch.object(w, 'stage_commands') as stages:
            data, stderr = self.invoke(args)
        self.assertEqual(data['outcome']['kind'], 'refused')
        self.assertEqual(data['outcome']['code'], 'ENV_UNMET')
        self.assertEqual(data['exit']['code'], 3)
        self.assertTrue(any(row['state']=='fail' for row in data['result']['checks']))
        self.assertFalse(self.results.exists()); self.assertFalse(self.metadata.exists())
        self.assertTrue(all(not artifact['written'] for artifact in data['artifacts']))
        stages.assert_not_called(); self.assertNotIn('Traceback', stderr)

    def test_run_rechecks_structured_gate_even_if_ready_is_true(self):
        preflight = {**self.preflight, 'ready': True, 'checks': [{'id': 'database', 'state': 'skipped', 'detail': {}}]}
        with patch.object(w, 'run_preflight', return_value=preflight), patch.object(w, 'stage_commands') as stages:
            with self.assertRaises(Refusal):
                w.run_workflow(self.inputs.parent, self.results, self.metadata, self.root/'db', self.manifest,
                    self.root/'env', ['alpha'], 1, 'sandbox')
        self.assertFalse(self.results.exists()); self.assertFalse(self.metadata.exists()); stages.assert_not_called()

    def test_envelope_cannot_replace_sample_events_status_or_summary(self):
        args = ['run', '--input-dir', str(self.inputs.parent), '--results-dir', str(self.results), '--metadata-dir', str(self.metadata),
            '--env-dir', str(self.root/'env'), '--db-dir', str(self.root/'db'), '--expected-manifest', str(self.manifest),
            '--samples', 'alpha', '--threads', '1', '--profile', 'sandbox']
        for path in (self.metadata/'alpha/events.jsonl', self.metadata/'alpha/stage_status.json',
                     self.metadata/'workflow_summary.json', self.metadata/'alpha/scientific_summary'):
            with patch.object(w, 'run_preflight') as preflight:
                data, _ = self.invoke(args+['--envelope-out', str(path)])
            self.assertEqual(data['outcome']['code'], 'PATHS_OVERLAP')
            self.assertFalse(self.metadata.exists()); self.assertFalse(self.results.exists())
            preflight.assert_not_called()

    def test_unavailable_log_remains_a_failed_stage_and_is_indexed(self):
        args = ['run', '--input-dir', str(self.inputs.parent), '--results-dir', str(self.results), '--metadata-dir', str(self.metadata),
            '--env-dir', str(self.root/'env'), '--db-dir', str(self.root/'db'), '--expected-manifest', str(self.manifest),
            '--samples', 'alpha', '--threads', '1', '--profile', 'sandbox']
        original = Path.open
        def open_path(path, mode='r', *args, **kwargs):
            if mode=='w' and path.suffix=='.log': raise PermissionError('synthetic log-open failure')
            return original(path, mode, *args, **kwargs)
        with patch.object(w, 'run_preflight', return_value=self.preflight), patch.object(w, 'stage_commands', side_effect=self.commands()), patch.object(Path, 'open', new=open_path):
            data, stderr = self.invoke(args)
        self.assertEqual(data['outcome']['kind'], 'failed')
        self.assertIn('log_tail_error', data['result']['failures'][0])
        self.assertTrue(any(a['role']=='stage_log' and not a['written'] for a in data['artifacts']))
        self.assertNotIn('Traceback', stderr)

    def test_event_write_defect_removes_completion_marker_and_propagates(self):
        def event(path, run_id, sample, stage, event_name, **details):
            if event_name=='run_succeeded': raise OSError('synthetic event write failure')
            append_event(path, run_id, sample, stage, event_name, **details)
        with patch.object(w, 'run_preflight', return_value=self.preflight), patch.object(w, 'stage_commands', side_effect=self.commands()), patch.object(w, 'append_event', side_effect=event):
            with self.assertRaisesRegex(OSError, 'synthetic event write failure'):
                w.run_workflow(self.inputs.parent, self.results, self.metadata, self.root/'db', self.manifest,
                    self.root/'env', ['alpha'], 1, 'sandbox')
        self.assertFalse((self.metadata/'alpha/completion.json').exists())
        status = json.loads((self.metadata/'alpha/stage_status.json').read_text())
        self.assertEqual(status['run']['state'], 'failed')
        self.assertEqual(status['failure']['code'], 'INTERNAL_ERROR')
        self.assertEqual(self.events('alpha')[-1]['event'], 'run_failed')

    def test_readiness_claims_follow_checks_without_attesting_search_execution(self):
        from dbcan_claims import derive_claims
        from dbcan_outcomes import CommandResult, NegativeResult
        self.ready_environment()
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe):
            ready, _ = self.invoke(self.preflight_args())
        self.assertIn('CL-P1', [row['id'] for row in ready['claims']['may_say']])
        self.assertNotIn('CL-A1', [row['id'] for row in ready['claims']['may_say']])
        self.assertIn('CL-N1', [row['id'] for row in ready['claims']['may_not_say']])
        (self.env/'bin/diamond').unlink()
        with patch.object(w.subprocess, 'run', side_effect=self.runtime_probe):
            unmet, _ = self.invoke(self.preflight_args())
        self.assertIn('CL-P2', [row['id'] for row in unmet['claims']['may_say']])
        self.assertNotIn('CL-P1', [row['id'] for row in unmet['claims']['may_say']])
        claims = derive_claims('preflight', {'kind': 'ok'}, {'structure': 'not_assessed', 'attestation': 'not_applicable'},
            {'ready': True, 'checks': [{'id': 'blocked', 'state': 'skipped'}]})
        self.assertNotIn('CL-P1', [row['id'] for row in claims['may_say']])
        typed = CommandResult.from_exception(NegativeResult('PREFLIGHT_UNMET', 'Readiness is unmet.'))
        self.assertEqual(typed.evidence['structure'], 'not_assessed')

    def test_preflight_envelope_must_not_dirty_future_run_destinations(self):
        self.ready_environment()
        with patch.object(w.subprocess, 'run') as probes:
            data, _ = self.invoke(self.preflight_args()+['--envelope-out', str(self.metadata/'preflight.json')])
        self.assertEqual(data['outcome']['code'], 'PATHS_OVERLAP')
        self.assertFalse(self.metadata.exists()); self.assertFalse(self.results.exists())
        probes.assert_not_called()

if __name__ == '__main__': unittest.main()
