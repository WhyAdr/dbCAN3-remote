"""Contract-level regression tests; never require dbCAN or databases."""
from __future__ import annotations
import ast
import contextlib
import io
import json
import os
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
from dbcan_outcomes import *
try:
    if os.environ.get('DBCAN_TEST_NO_JSONSCHEMA'): raise ImportError
    import jsonschema
except ImportError:
    jsonschema = None


def check_envelope(test, env):
    schema = json.loads((ROOT/'schemas/envelope.v1.schema.json').read_text())
    test.assertEqual(set(env), set(schema['required']))
    test.assertEqual(env['contract_version'], 1)
    test.assertIn(env['outcome']['kind'], EXIT_CODES)
    test.assertIn(env['evidence']['structure'], ['valid', 'invalid', 'not_assessed'])
    test.assertIn(env['evidence']['attestation'], ['attested', 'unattested', 'rejected', 'not_applicable'])
    if jsonschema: jsonschema.Draft202012Validator(schema).validate(env)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fx = self.root/'native'
        shutil.copytree(ROOT/'tests/fixtures/zero_hit', self.fx)
        self.common = ['--faa', str(self.fx/'inputs/sample.faa'), '--gff', str(self.fx/'inputs/sample.gff3')]
        self.args = ['validate', *self.common, '--results-dir', str(self.fx/'results'), '--metadata-dir', str(self.root/'diag')]

    def call(self, args, env=None):
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/dbcan_workflow.py'), *args],
            capture_output=True, text=True, env={**os.environ, 'DBCAN_WORKFLOW_EXIT_POLICY': 'strict', **(env or {})})
        data = json.loads(result.stdout)
        check_envelope(self, data)
        self.assertEqual(result.returncode, data['exit']['code'])
        if data['outcome']['kind'] != 'error': self.assertNotIn('Traceback', result.stderr)
        return data

    def tree(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')), w._hash_tree(self.root)

    def test_examples_conform(self):
        for path in (ROOT/'tests/data').glob('*.json'):
            with self.subTest(path=path): check_envelope(self, json.loads(path.read_text()))

    def test_acceptance_probes_and_refusal_side_effects(self):
        for suffix, code in [([], 'ATTESTATION_REQUIRED'), (['--metadata-dir', str(self.fx/'results/diag'), '--allow-unattested'], 'PATHS_OVERLAP'),
                              (['--results-dir', str(self.root/'absent'), '--allow-unattested'], 'RESULTS_DIR_MISSING')]:
            with self.subTest(code=code):
                before = self.tree()
                data = self.call(self.args+suffix)
                self.assertEqual(data['outcome'], {'kind': 'refused', 'code': code, 'summary': data['outcome']['summary']})
                self.assertEqual(data['exit']['code'], 3)
                self.assertEqual(self.tree(), before)
                self.assertNotIn('None', data['refusal']['message'])
        data = self.call(['validate', '--faa', 'missing'])
        self.assertEqual(data['outcome']['kind'], 'usage')
        self.assertEqual(data['exit']['code'], 2)

    def test_valid_zero_hit_result_and_persistence(self):
        data = self.call(self.args+['--allow-unattested'])
        self.assertEqual(data['evidence'], {'structure': 'valid', 'attestation': 'unattested'})
        self.assertEqual(data['result']['overview_candidates'], 0)
        self.assertEqual(data['result']['legacy_status'], 'structurally_valid_execution_unattested')
        persisted = self.root/'diag/envelope.validate.json'
        self.assertTrue(persisted.is_file())
        artifact = next(a for a in data['artifacts'] if a['path'] == str(persisted))
        self.assertEqual(artifact['sha256'], w.sha256_file(persisted))
        original = w.validate_outputs(self.fx/'inputs/sample.faa', self.fx/'inputs/sample.gff3', self.fx/'results', require_stage_status=False)
        result = dict(data['result']); result['status'] = result.pop('legacy_status')
        for key, value in original.items(): self.assertEqual(result[key], value)

    def test_exit_projection_all_kinds(self):
        for policy in ['strict', 'semantic-zero']:
            for kind, code in EXIT_CODES.items():
                with self.subTest(policy=policy, kind=kind):
                    cr = CommandResult(kind=kind, code='OK' if kind=='ok' else 'INTERNAL_ERROR')
                    data = cli.build_envelope('validate', cr, policy)
                    expected = 0 if policy=='semantic-zero' and kind in {'ok','negative','refused','failed'} else code
                    self.assertEqual(data['exit']['code'], expected)
        data = self.call(self.args+['--exit-policy', 'semantic-zero'])
        self.assertEqual(data['outcome']['kind'], 'refused'); self.assertEqual(data['exit']['code'], 0)
        data = self.call(self.args, {'DBCAN_WORKFLOW_EXIT_POLICY': 'semantic-zero'})
        self.assertEqual(data['exit']['code'], 0)

    def test_negative_content_and_unexpected_defect(self):
        path = self.fx/'results/overview.tsv'
        path.write_text('bad\theader\n')
        data = self.call(self.args+['--allow-unattested'])
        self.assertEqual(data['outcome']['kind'], 'negative')
        self.assertEqual(data['evidence']['structure'], 'invalid')
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, 'dispatch', side_effect=RuntimeError('synthetic defect')), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(self.args+['--allow-unattested'])
        self.assertEqual(code, 1); self.assertEqual(json.loads(out.getvalue())['outcome']['kind'], 'error')
        self.assertIn('Traceback', err.getvalue())

    def test_explicit_envelope_and_protected_output(self):
        path = self.root/'envelopes/refusal.json'
        data = self.call(self.args+['--envelope-out', str(path)])
        self.assertEqual(data['outcome']['code'], 'ATTESTATION_REQUIRED'); self.assertTrue(path.exists())
        self.assertFalse((self.root/'diag').exists())
        before = self.tree()
        data = self.call(self.args+['--allow-unattested', '--envelope-out', str(self.fx/'inputs/sample.faa')])
        self.assertEqual(data['outcome']['code'], 'PATHS_OVERLAP'); self.assertEqual(self.tree(), before)

    def bound_status(self, v2=False):
        data = json.loads((self.fx/'metadata/stage_status.template.json').read_text())
        data.update(run_id='bound-test', input_faa_sha256=w.sha256_file(self.fx/'inputs/sample.faa'),
            input_gff_sha256=w.sha256_file(self.fx/'inputs/sample.gff3'), results_dir=str(self.fx/'results'))
        data['stages'][w.STAGE_NAMES[-1]]['output_sha256'] = w._hash_tree(self.fx/'results')
        if v2: data = w._v2_status_document(data)
        path = self.root/'status.json'; path.write_text(json.dumps(data)); return path

    def test_legacy_and_v2_status_binding_and_rejections(self):
        for v2 in [False, True]:
            status = self.bound_status(v2)
            env = self.call(self.args+['--status-file', str(status)])
            self.assertEqual(env['evidence']['attestation'], 'attested')
            self.assertEqual(env['run_id'], 'bound-test')
        for content in ['not JSON', '[]', '{"schema_version":2,"run":{"state":"failed"}}']:
            status.write_text(content)
            before = self.tree()
            env = self.call(self.args+['--status-file', str(status), '--allow-unattested'])
            self.assertEqual(env['outcome']['code'], 'ATTESTATION_REJECTED')
            self.assertEqual(env['evidence']['attestation'], 'rejected')
            self.assertEqual(self.tree(), before)
        env = self.call(self.args+['--status-file', str(self.root/'absent'), '--allow-unattested'])
        self.assertEqual(env['outcome']['code'], 'ATTESTATION_REJECTED')

    def test_claims_are_deterministic_and_bind_structured_evidence(self):
        from dbcan_claims import CLAIMS, derive_claims
        unattested = derive_claims('validate', {'kind': 'ok'}, {'structure': 'valid', 'attestation': 'unattested'}, {'sample_source': 'faa_stem'})
        self.assertIn('CL-N1', [c['id'] for c in unattested['may_not_say']])
        self.assertIn('CL-N9', [c['id'] for c in unattested['may_not_say']])
        self.assertNotIn('CL-A1', [c['id'] for c in unattested['may_say']])
        attested = derive_claims('validate', {'kind': 'ok'}, {'structure': 'valid', 'attestation': 'attested'}, {})
        self.assertIn('CL-A1', [c['id'] for c in attested['may_say']])
        self.assertIn('CL-N10', [c['id'] for c in attested['may_not_say']])
        for kind in ['refused', 'failed', 'usage', 'error']:
            claims = derive_claims('validate', {'kind': kind}, {'structure': 'not_assessed', 'attestation': 'not_applicable'}, {})
            self.assertIn('CL-N0', [c['id'] for c in claims['may_not_say']])
        summary = derive_claims('summarize', {'kind': 'ok'}, {'structure': 'valid', 'attestation': 'unattested'}, {'substrate_rows': 1})
        self.assertTrue({'CL-N3','CL-N4','CL-N5','CL-N6','CL-N7','CL-N11'} <= {c['id'] for c in summary['may_not_say']})
        for side in summary.values(): self.assertEqual([c['id'] for c in side], sorted(c['id'] for c in side))
        for info in REGISTRY.values():
            for remedy in info['remediation']:
                self.assertTrue(set(remedy['claim_effects']) <= set(CLAIMS))

    def test_exception_registry_and_legacy_types(self):
        for code, info in REGISTRY.items():
            if info['kind'] in {'refused', 'negative', 'failed', 'usage'}:
                typ = {'refused': Refusal, 'negative': NegativeResult, 'failed': StageFailure, 'usage': UsageError}[info['kind']]
                exc = typ(code, info['summary'])
                self.assertEqual(exc.code, code)
                self.assertEqual(CommandResult.from_exception(exc).kind, info['kind'])
        self.assertIsInstance(MissingPathRefusal('INPUT_MISSING', 'Missing input.'), FileNotFoundError)
        self.assertIsInstance(ExistingPathRefusal('PATHS_OVERLAP', 'Existing output.'), FileExistsError)
        self.assertIsInstance(Refusal('PATHS_OVERLAP', 'Overlap.'), ValueError)

if __name__ == '__main__': unittest.main()
