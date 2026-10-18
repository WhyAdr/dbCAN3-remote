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

if __name__ == '__main__': unittest.main()
