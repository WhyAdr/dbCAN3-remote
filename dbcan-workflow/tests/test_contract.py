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
        self.assertIn(data['outcome']['code'], cli.describe_commands()['commands'][data['command']]['outcome_codes'])
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
                self.assertEqual(data['outcome'], {'kind': 'refused', 'code': code, 'summary': REGISTRY[code]['summary']})
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

    def test_registry_covers_typed_raise_sites_and_docs_stay_in_sync(self):
        typed = {'Refusal','MissingPathRefusal','ExistingPathRefusal','RuntimeRefusal','NegativeResult','MissingDataResult','StageFailure','UsageError'}
        for path in (ROOT/'scripts').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in typed:
                    if node.args and isinstance(node.args[0], ast.Constant):
                        self.assertIn(node.args[0].value, REGISTRY, (path, node.lineno))
        subprocess.run([sys.executable, '-B', str(ROOT/'scripts/gen_docs.py'), '--check'], check=True)

    def test_every_public_parser_argument_has_help(self):
        import argparse
        def walk(parser):
            for action in parser._actions:
                self.assertTrue(action.help, action.dest)
                if isinstance(action, argparse._SubParsersAction):
                    for sub in action.choices.values(): walk(sub)
        walk(w.build_parser())

    def test_database_difference_is_bounded_and_complete_diff_is_guarded(self):
        db = self.root/'emptydb'; db.mkdir()
        args = ['verify-db','--db-dir',str(db),'--expected-manifest', str(ROOT/'environment/database_v5-2-9_5-5-2026.expected.sha256'), '--observed-manifest', str(self.root/'observed.sha256')]
        data = self.call(args+['--diff-out',str(self.root/'diff.json')])
        self.assertEqual(data['outcome']['kind'], 'negative')
        self.assertEqual(data['result']['missing_count'], 646)
        self.assertEqual(len(data['result']['listed']['missing']), 20)
        self.assertEqual(len(json.loads((self.root/'diff.json').read_text())['missing']), 646)
        without_diff = self.call(args)
        self.assertLess(len(json.dumps(without_diff, indent=2).encode()), 4096)
        data = self.call(args+['--diff-out', str(db/'overwrite.json')])
        self.assertEqual(data['outcome']['code'], 'PATHS_OVERLAP')
        data = self.call(args+['--max-listed', '-1'])
        self.assertEqual(data['outcome']['kind'], 'usage')

    def test_sibling_shims_match_subcommands_and_warn_for_aliases(self):
        audit_args = ['--gff',str(self.fx/'inputs/sample.gff3'),'--processed-gff',str(self.fx/'results/cgc.gff'),
            '--out-json',str(self.root/'audit/data.json'),'--out-tsv',str(self.root/'audit/data.tsv')]
        public = self.call(['audit-circular', *audit_args])
        shim = subprocess.run([sys.executable,'-B',str(ROOT/'scripts/audit_circular_windows.py'), *audit_args], capture_output=True,text=True)
        self.assertEqual(public['result'], json.loads(shim.stdout)['result'])
        alias = self.call(['audit-circular', *[x.replace('--out-json','--json').replace('--out-tsv','--tsv') for x in audit_args]])
        self.assertEqual({x['code'] for x in alias['warnings']}, {'DEPRECATED_FLAG_JSON', 'DEPRECATED_FLAG_TSV'})
        self.assertEqual(len(alias['warnings']), 2)
        args = ['--processed-gff',str(self.fx/'results/cgc.gff'),'--native-members',str(self.fx/'results/cgc_standard_out.tsv'),
            '--native-summary',str(self.fx/'results/cgc_standard_out_summary.tsv'),
            '--corrected-members',str(self.root/'overlay/members.tsv'),'--corrected-summary',str(self.root/'overlay/summary.tsv'),
            '--changes',str(self.root/'overlay/changes.tsv'),'--report',str(self.root/'overlay/report.json'),'--dbcan-version','5.2.9']
        public = self.call(['cgc-overlay', *args])
        shim = subprocess.run([sys.executable,'-B',str(ROOT/'scripts/exact_cgc_categories.py'), *args], capture_output=True,text=True)
        self.assertEqual(public['result'], json.loads(shim.stdout)['result'])
        before = self.tree()
        refused = self.call(['cgc-overlay', *args[:-1], '5.3.0'])
        self.assertEqual(refused['outcome']['code'], 'VERSION_UNSUPPORTED')
        self.assertEqual(self.tree(), before)

    def test_describe_matches_parser_wrapper_and_safety_metadata(self):
        import re
        data = self.call(['describe'])['result']
        self.assertEqual(set(data['commands']), set(w.COMMAND_METADATA))
        for name, meta in data['commands'].items():
            self.assertEqual(meta['requires_user_confirmation'], name=='run')
            self.assertFalse(meta['needs_network'])
        usage = re.search(r'Usage: run_dbcan_workflow.sh <([^>]+)>', (ROOT/'scripts/run_dbcan_workflow.sh').read_text()).group(1)
        self.assertEqual(set(usage.split('|')), set(data['commands']))
        self.assertEqual(data['database_stage_assets'], {key: list(value) for key,value in w.DB_ASSETS_BY_STAGE.items()})

    def test_explicit_sample_labels_and_duplicate_run_samples(self):
        inferred = self.call(self.args+['--allow-unattested'])
        self.assertEqual(inferred['result']['sample_source'], 'faa_stem')
        self.assertIn('CL-N9', [c['id'] for c in inferred['claims']['may_not_say']])
        for command in ['validate','summarize']:
            args = [command, *self.args[1:], '--sample-id', 'isolate-A']
            if command=='validate': args.append('--allow-unattested')
            data = self.call(args)
            self.assertEqual(data['result']['sample'], 'isolate-A')
            self.assertEqual(data['result']['sample_source'], 'explicit')
            self.assertNotIn('SAMPLE_INFERRED', [x['code'] for x in data['warnings']])
        before = self.tree()
        data = self.call(['run','--input-dir',str(self.fx),'--results-dir',str(self.root/'newresults'),'--metadata-dir',str(self.root/'newmeta'),
            '--db-dir',str(self.root/'db'),'--env-dir',str(self.root/'env'),'--expected-manifest',str(self.root/'expected.sha256'),
            '--samples','dup','dup','--threads','1','--profile','sandbox'])
        self.assertEqual(data['outcome']['code'], 'SAMPLE_ID_UNSAFE')
        self.assertEqual(before, self.tree())

    def test_archived_manifest_digest_consistency(self):
        digest = w.sha256_file(ROOT/'environment/database_v5-2-9_5-5-2026.expected.sha256')
        self.assertEqual(digest, w.ARCHIVED_MANIFEST_SHA256)
        import re
        for path in ROOT.rglob('*.md'):
            for quoted in re.findall(r'[0-9a-f]{64}', path.read_text()):
                # Documents quoting the archived digest must quote its exact value.
                if quoted.startswith(digest[:16]): self.assertEqual(quoted, digest, path)
        self.assertNotIn('SNAPSHOT_BASE_URL =', (ROOT/'scripts/dbcan_workflow.py').read_text())

    def test_wrapper_pre_python_failures_emit_static_usage_envelopes(self):
        for interpreter, args in [('', ['validate']), ('/nonexistent', ['validate']), (sys.executable, [])]:
            result = subprocess.run(['bash', str(ROOT/'scripts/run_dbcan_workflow.sh'), *args], capture_output=True,text=True,
                env={**os.environ, 'DBCAN_PYTHON': interpreter})
            self.assertEqual(result.returncode, 2)
            data = json.loads(result.stdout); check_envelope(self,data)
            self.assertEqual(data['outcome']['kind'], 'usage')

    def test_json_atomic_mode_respects_umask(self):
        old = os.umask(0o022)
        try:
            path = self.root/'mode.json'; w.write_json_atomic(path, {'ok': True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        finally: os.umask(old)

    def test_colliding_artifact_slots_and_refusal_inventory_are_safe(self):
        target = self.root/'diag/output_validation.json'
        for extra in [['--observed-manifest',str(target)], ['--envelope-out',str(target)]]:
            before = self.tree()
            data = self.call(self.args+['--allow-unattested',*extra])
            self.assertEqual(data['outcome']['code'],'PATHS_OVERLAP')
            self.assertTrue(all(not artifact['written'] for artifact in data['artifacts']))
            self.assertEqual(self.tree(),before)
        protected = self.fx/'inputs/sample.faa'
        data = self.call(self.args+['--envelope-out',str(protected)])
        self.assertTrue(all(not artifact['written'] for artifact in data['artifacts']))
        data = self.call(['summarize',*self.args[1:],'--envelope-out',str(self.root/'diag/summary.json')])
        self.assertEqual(data['outcome']['code'],'PATHS_OVERLAP')

    def test_malformed_gff_numbers_are_negative_and_manifest_types_reject(self):
        path = self.fx/'inputs/sample.gff3'
        path.write_text(path.read_text().replace('100', 'invalid', 1))
        data = self.call(self.args+['--allow-unattested'])
        self.assertEqual(data['outcome']['kind'],'negative')
        shutil.copy2(ROOT/'tests/fixtures/zero_hit/inputs/sample.gff3',path)
        for key,value in [('run_id',123),('results_dir',123),('schema_version',True)]:
            status=self.bound_status(True); record=json.loads(status.read_text()); record[key]=value; status.write_text(json.dumps(record))
            data=self.call(self.args+['--status-file',str(status),'--allow-unattested'])
            self.assertEqual(data['outcome']['code'],'ATTESTATION_REJECTED')

    def test_failed_stage_emits_contract_and_indexes_original_logs(self):
        inputs=self.root/'run_inputs/original'; inputs.mkdir(parents=True)
        for suffix in ['faa','gff3']: shutil.copy2(self.fx/('inputs/sample.'+suffix),inputs/('sample.'+suffix))
        manifest=self.root/'manifest.sha256'; manifest.write_text('synthetic preflight fixture')
        args=['run','--input-dir',str(inputs.parent),'--results-dir',str(self.root/'run_results'), '--metadata-dir',str(self.root/'run_meta'),
            '--env-dir',str(self.root/'env'),'--db-dir',str(self.root/'db'),'--expected-manifest',str(manifest),'--samples','sample','--threads','1','--profile','sandbox']
        def commands(*a,**kw):
            return [(name,[sys.executable,'-c','raise SystemExit(9)'],a[6]/(name+'.log')) for name in w.STAGE_NAMES]
        preflight={'database':{'manifest_check':{'snapshot':'synthetic'}}}
        stdout,stderr=io.StringIO(),io.StringIO()
        with patch.object(w,'run_preflight',return_value=preflight),patch.object(w,'stage_commands',side_effect=commands),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            exit_code=cli.main(args)
        data=json.loads(stdout.getvalue());check_envelope(self,data)
        self.assertEqual(exit_code,5);self.assertEqual(data['outcome']['kind'],'failed')
        self.assertTrue(any(a['role']=='stage_log' and a['written'] and '/run_results/sample/logs/' in a['path'] for a in data['artifacts']))
        self.assertNotIn('Traceback',stderr.getvalue())
        status=json.loads((self.root/'run_meta/sample/stage_status.json').read_text())
        self.assertEqual(status['run']['state'],'failed')
        self.assertEqual(status['schema_version'],2)

    def test_output_ancestors_and_directory_targets_refuse_before_writes(self):
        existing = self.root/'directory'; existing.mkdir()
        for json_path,tsv_path in [(existing,self.root/'other.tsv'), (self.root/'parent',self.root/'parent/child.tsv')]:
            before=self.tree()
            env=self.call(['audit-circular','--gff',str(self.fx/'inputs/sample.gff3'),'--processed-gff',str(self.fx/'results/cgc.gff'),
                '--out-json',str(json_path),'--out-tsv',str(tsv_path)])
            self.assertEqual(env['outcome']['code'],'PATHS_OVERLAP')
            self.assertEqual(before,self.tree())

    def test_actual_preconditions_emit_registered_refusal_codes(self):
        db=self.root/'db';db.mkdir()
        manifest=self.root/'unsafe.sha256';manifest.write_text('0'*64+'  ../escape\n')
        env=self.call(['verify-db','--db-dir',str(db),'--expected-manifest',str(manifest),'--observed-manifest',str(self.root/'obs.sha256')])
        self.assertEqual(env['outcome']['code'],'MANIFEST_PATH_UNSAFE')
        env=self.call(['verify-db','--db-dir',str(self.root/'missingdb'),'--expected-manifest',str(manifest),'--observed-manifest',str(self.root/'obs.sha256')])
        self.assertEqual(env['outcome']['code'],'DB_UNVERIFIED')
        pre=['preflight',*self.common,'--env-dir',str(self.root/'env'),'--db-dir',str(db),'--expected-manifest',str(manifest),
            '--threads','1','--profile','sandbox','--results-dir',str(self.root/'future-results'),'--metadata-dir',str(self.root/'future-metadata')]
        env=self.call(pre);self.assertEqual(env['outcome']['code'],'PREFLIGHT_UNMET')
        self.assertTrue(any(row['state']=='fail' and row['detail']['code']=='ENV_UNMET' for row in env['result']['checks']))
        with patch.object(w,'effective_resources',return_value={'effective_cpu_allocation':1}),self.assertRaises(Refusal) as caught:
            w.run_preflight(self.fx/'inputs/sample.faa',self.fx/'inputs/sample.gff3',self.root/'env/bin/python', self.root/'env/bin/run_dbcan',self.root/'env/bin/diamond',db,manifest,2,'sandbox',self.root/'r',self.root/'m')
        self.assertEqual(caught.exception.code,'THREADS_EXCEED_ALLOCATION')
        path=self.fx/'inputs/sample.gff3';path.write_text(path.read_text().replace('ID=p1','ID=other'))
        env=self.call(self.args+['--allow-unattested']);self.assertEqual(env['outcome']['code'],'INPUT_MISMATCH')
        env=self.call(self.args+['--faa',str(self.root/'missinginputs/nonexistent.faa'),'--allow-unattested'])
        self.assertEqual(env['outcome']['code'],'INPUT_MISSING')

    def test_environment_probe_failures_refuse_with_plain_messages(self):
        env=self.root/'fakeenv';(env/'bin').mkdir(parents=True)
        for name in ['python','run_dbcan','diamond']:
            path=env/'bin'/name;path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755)
        def preflight():
            return w.run_preflight(self.fx/'inputs/sample.faa',self.fx/'inputs/sample.gff3',env/'bin/python',env/'bin/run_dbcan',env/'bin/diamond',
                self.root/'db',self.root/'expected.sha256',1,'sandbox',self.root/'results',self.root/'metadata')
        with self.assertRaises(Refusal) as caught: preflight()
        self.assertEqual(caught.exception.code,'ENV_UNMET')
        self.assertEqual(str(caught.exception),'The selected Python probe returned malformed runtime metadata.')
        with patch.object(w.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','None: traceback text')),self.assertRaises(Refusal) as caught: preflight()
        self.assertEqual(caught.exception.code,'ENV_UNMET')
        self.assertEqual(str(caught.exception),'The selected Python smoke test failed.')
        runtime=subprocess.CompletedProcess([],0,json.dumps({'python':'3.12','machine':'x86_64','prefix':str(env),'dbcan':'5.2.9','packages':{}}),'')
        with patch.object(w.subprocess,'run',side_effect=[runtime,subprocess.CompletedProcess([],0,'bad','')]),self.assertRaises(Refusal) as caught: preflight()
        self.assertEqual(str(caught.exception),'The run_dbcan version probe failed or was not 5.2.9.')
        with patch.object(w.subprocess,'run',side_effect=[runtime,subprocess.CompletedProcess([],0,'5.2.9',''),subprocess.CompletedProcess([],0,'bad','')]),self.assertRaises(Refusal) as caught: preflight()
        self.assertEqual(str(caught.exception),'The DIAMOND version probe failed or was not 2.2.8.')
        with patch.object(w.subprocess,'run',side_effect=OSError('cannot start')),self.assertRaises(Refusal) as caught: preflight()
        self.assertEqual(str(caught.exception),'A selected runtime probe could not start.')

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
