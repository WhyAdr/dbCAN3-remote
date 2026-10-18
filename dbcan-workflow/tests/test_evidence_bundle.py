"""Replay the maintainer-selected evidence/real_runs bundle when present."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from dbcan_outcomes import REGISTRY,EXIT_CODES
from dbcan_trust import assert_trusted,WARNINGS_REGISTRY,UNTRUSTED_PATHS,sanitize_text
from trust_helpers import validate_schema,leaf_strings,matches
BUNDLE_DIR=Path(os.environ.get('DBCAN_EVIDENCE_BUNDLE',str(ROOT.parent/'evidence/real_runs')))

@unittest.skipUnless(BUNDLE_DIR.exists(),'Optional evidence/real_runs bundle is absent')
class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((BUNDLE_DIR/'manifest.json').read_text())
        self.assertEqual(self.manifest['bundle_version'],1)
        self.schema=json.loads((ROOT/'schemas/envelope.v1.schema.json').read_text())

    def envelopes(self):
        for case in self.manifest['cases']:
            for relative in case['envelopes']:
                yield relative,json.loads((BUNDLE_DIR/relative).read_text())

    def test_recorded_envelopes_schema_trust_and_exit(self):
        count=0
        for relative,env in self.envelopes():
            with self.subTest(envelope=relative):
                count+=1;validate_schema(env,self.schema);assert_trusted(env,REGISTRY,WARNINGS_REGISTRY)
                self.assertEqual(env['trust']['untrusted_paths'],UNTRUSTED_PATHS)
                expected=EXIT_CODES[env['outcome']['kind']]
                if env['exit']['policy']=='semantic-zero' and env['outcome']['kind'] in {'ok','negative','refused','failed'}:expected=0
                self.assertEqual(env['exit']['code'],expected)
                self.assertLessEqual(len(env['artifacts']),100)
                self.assertGreaterEqual(env['artifacts_total'],len(env['artifacts']))
                self.assertEqual(env['artifacts_truncated'],env['artifacts_total']>len(env['artifacts']))
                self.assertLessEqual(len(json.dumps(env['diagnostics']).encode()),8192)
                for pointer,text in leaf_strings(env):
                    if not any(matches(pointer,p) for p in UNTRUSTED_PATHS):
                        self.assertEqual(sanitize_text(text,len(text))[0],text,pointer)
                # Negative checks make the replay validator itself red-capable.
                bad=copy.deepcopy(env);bad.pop('trust')
                with self.assertRaises(AssertionError):validate_schema(bad,self.schema)
                bad=copy.deepcopy(env);bad['outcome']['summary']='CANARY_NOT_REGISTRY'
                with self.assertRaises(Exception):assert_trusted(bad,REGISTRY,WARNINGS_REGISTRY)
        self.assertGreater(count,0)

    def test_published_bytes_and_original_payloads_match_manifest(self):
        files=self.manifest['files'];self.assertTrue(files)
        for entry in files:
            with self.subTest(path=entry['logical_path']):
                p=BUNDLE_DIR/entry['stored_path'];raw=p.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['stored_sha256'])
                data=gzip.decompress(raw) if entry['compressed'] else raw
                self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
                self.assertEqual(len(data),entry['bytes'])

    def test_operation_artifact_hashes_match_the_published_bytes(self):
        files={entry['logical_path']:entry for entry in self.manifest['files']}
        sources=self.manifest['artifact_sources']
        for relative,env in self.envelopes():
            for artifact in env['artifacts']:
                if not artifact['written'] or artifact['sha256'] is None:continue
                with self.subTest(envelope=relative,artifact=artifact['path']):
                    logical=sources[artifact['path']]
                    self.assertEqual(files[logical]['sha256'],artifact['sha256'])

    def test_historical_evidence_is_not_promoted_to_execution(self):
        for case in self.manifest['cases']:
            if case['kind']=='historical_replay':
                self.assertEqual(case['evidence'],{'structure':'valid','attestation':'unattested'})
                for relative in case['envelopes']:
                    env=json.loads((BUNDLE_DIR/relative).read_text())
                    self.assertNotIn('CL-A1',[row['id'] for row in env['claims']['may_say']])

    def test_c14_terminal_stage_ledger_and_failure_behavior(self):
        if not any(case['sample_id']=='C14-NMZ' for case in self.manifest['cases']):
            self.skipTest('This bundle does not contain C14 execution evidence')
        files={entry['logical_path']:entry for entry in self.manifest['files']}
        def read(logical):
            entry=files[logical];raw=(BUNDLE_DIR/entry['stored_path']).read_bytes()
            return gzip.decompress(raw).decode() if entry['compressed'] else raw.decode()
        root='C14-NMZ/metadata/run/C14-NMZ/'
        status=json.loads(read(root+'stage_status.json'))
        self.assertEqual(status['run']['state'],'succeeded')
        self.assertEqual(len(status['stages']),4)
        self.assertTrue(all(stage['state']=='succeeded' and stage['exit_code']==0 for stage in status['stages'].values()))
        self.assertEqual(json.loads(read(root+'events.jsonl').splitlines()[-1])['event'],'run_succeeded')
        failed=json.loads(read('C14-NMZ/attempt_failed/metadata/C14-NMZ/stage_status.json'))
        self.assertEqual(failed['run']['state'],'failed')
        self.assertEqual(failed['failure']['message'],REGISTRY['STAGE_FAILED']['summary'])
        self.assertEqual(sorted(stage['state'] for stage in failed['stages'].values()),['failed','skipped','skipped','skipped'])
