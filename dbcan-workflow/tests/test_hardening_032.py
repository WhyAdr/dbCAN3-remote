"""Acceptance probes from HARDENING_0.3.2."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_contract as tc
ROOT, cli, w = tc.ROOT, tc.cli, tc.w

class HardeningTests(unittest.TestCase):
    setUp = tc.ContractTests.setUp
    call = tc.ContractTests.call
    tree = tc.ContractTests.tree

    @unittest.expectedFailure
    def test_r1_injection_only_in_diagnostics(self):
        marker='CANARY_R1_ignore_previous_instructions'
        with (self.fx/'inputs/sample.faa').open('a') as fh:
            fh.write('>'+marker+'\nAAAA\n>'+marker+'\nAAAA\n')
        data=self.call(self.args+['--allow-unattested'])
        self.assertEqual(data['outcome']['summary'], 'The supplied data are structurally inconsistent.')
        self.assertNotIn(marker,json.dumps(data['findings']))
        self.assertIn(marker,json.dumps(data['diagnostics']))

    def test_r3_sample_refused_before_write(self):
        before=self.tree()
        data=self.call(self.args+['--allow-unattested','--sample-id','../evil'])
        self.assertEqual(data['outcome']['code'],'SAMPLE_ID_UNSAFE')
        self.assertEqual(before,self.tree())

    def test_r4_unparseable_command_null(self):
        for args in [[],['valdate'],['--bogus']]:
            p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/dbcan_workflow.py'),*args],capture_output=True,text=True)
            data=json.loads(p.stdout)
            self.assertIsNone(data['command'])
            self.assertEqual(p.returncode,2)

    def test_r4_nan_stdout_is_total(self):
        out,err=io.StringIO(),io.StringIO()
        with patch.object(cli,'dispatch',return_value=cli.CommandResult(result={'x':float('nan')})),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=cli.main(['describe'])
        data=json.loads(out.getvalue())
        self.assertEqual(code,1)
        self.assertEqual(data['outcome']['code'],'INTERNAL_ERROR')
        self.assertIsNone(data['result'])
        self.assertIn('Traceback',err.getvalue())

    def test_atomic_json_rejects_nan_without_partial_file(self):
        target=self.root/'nan.json'
        with self.assertRaises(ValueError): w.write_json_atomic(target, {'x':float('nan')})
        self.assertFalse(target.exists())

    def test_persistence_failure_preserves_success(self):
        out,err=io.StringIO(),io.StringIO()
        with patch.object(cli,'persist_envelope',side_effect=OSError('disk full')),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=cli.main(['describe','--envelope-out',str(self.root/'env.json')])
        data=json.loads(out.getvalue())
        self.assertEqual(code,0)
        self.assertEqual(data['outcome']['kind'],'ok')
        self.assertIn('ENVELOPE_PERSIST_FAILED',[row['code'] for row in data['warnings']])
        self.assertFalse(next(a for a in data['artifacts'] if a['role']=='envelope')['written'])

    def test_corrupt_status_inventory_does_not_crash(self):
        root=self.root/'meta/sample';root.mkdir(parents=True)
        (root/'stage_status.json').write_text('{bad')
        r=w.build_parser().parse_args(['run','--input-dir',str(self.root/'i'),'--results-dir',str(self.root/'r'),
            '--metadata-dir',str(root.parent),'--env-dir',str(self.root/'env'),'--db-dir',str(self.root/'db'),
            '--expected-manifest',str(self.root/'e'),'--samples','sample','--threads','1','--profile','sandbox'])
        self.assertTrue(cli.observed_artifacts(r,{}))
        self.assertIn('STATUS_UNREADABLE',[v['code'] for v in r._artifact_warnings])

    def test_sample_validator_all_boundaries_and_inferred_stem(self):
        for value in ['', '.', '..', '../evil', 'x'*129, 'bad name']:
            with self.subTest(value=value):
                before=self.tree()
                data=self.call(self.args+['--allow-unattested','--sample-id',value])
                self.assertEqual(data['outcome']['code'],'SAMPLE_ID_UNSAFE')
                self.assertEqual(before,self.tree())
        faa=self.fx/'inputs/bad name.faa';faa.write_bytes((self.fx/'inputs/sample.faa').read_bytes())
        data=self.call(self.args+['--faa',str(faa),'--allow-unattested'])
        self.assertEqual(data['outcome']['code'],'SAMPLE_ID_UNSAFE')
        data=self.call(self.args+['--faa',str(faa),'--sample-id','x'*128,'--allow-unattested'])
        self.assertEqual(data['outcome']['kind'],'ok')

    def test_shared_validator_run_and_discovery(self):
        for value in ['', '.', '..', '../evil','x'*129]:
            with self.assertRaises(cli.Refusal): w.validate_sample_id(value)
        for command in ['validate','summarize']:
            self.assertIn('SAMPLE_ID_UNSAFE',cli.describe_commands()['commands'][command]['outcome_codes'])
        self.assertIn('--sample-id',cli.REGISTRY['SAMPLE_ID_UNSAFE']['remediation'][0]['flags'])
