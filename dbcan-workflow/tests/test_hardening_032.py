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

    @unittest.expectedFailure
    def test_r3_sample_refused_before_write(self):
        before=self.tree()
        data=self.call(self.args+['--allow-unattested','--sample-id','../evil'])
        self.assertEqual(data['outcome']['code'],'SAMPLE_ID_UNSAFE')
        self.assertEqual(before,self.tree())

    @unittest.expectedFailure
    def test_r4_unparseable_command_null(self):
        for args in [[],['valdate'],['--bogus']]:
            p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/dbcan_workflow.py'),*args],capture_output=True,text=True)
            data=json.loads(p.stdout)
            self.assertIsNone(data['command'])
            self.assertEqual(p.returncode,2)

    @unittest.expectedFailure
    def test_r4_nan_stdout_is_total(self):
        out,err=io.StringIO(),io.StringIO()
        with patch.object(cli,'dispatch',return_value=cli.CommandResult(result={'x':float('nan')})),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=cli.main(['describe'])
        data=json.loads(out.getvalue())
        self.assertEqual(code,1)
        self.assertEqual(data['outcome']['code'],'INTERNAL_ERROR')
        self.assertIsNone(data['result'])
        self.assertIn('Traceback',err.getvalue())
