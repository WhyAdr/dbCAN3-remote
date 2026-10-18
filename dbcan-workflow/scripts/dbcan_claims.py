"""Deterministic report claims derived solely from structured evidence."""
from __future__ import annotations
import re

COMMANDS = {'prepare','validate','summarize','verify-db','preflight','run','audit-circular','cgc-overlay','describe',None}
# Preserve existing scopes except the five maintainer-approved CL-N1 exclusions.
CLAIMS = {
 'CL-P1': {"text": 'All required preflight checks passed at assessment time.', "source": 'references/phase4-diagnostics.md', "anchor": '`result.ready` is true only when every required check passes.', "scope": COMMANDS},
 'CL-P2': {"text": 'The readiness check report completed; failed or skipped requirements remain.', "source": 'references/phase4-diagnostics.md', "anchor": 'A skipped row lists `blocked_by` check IDs; it is never a pass.', "scope": COMMANDS},
 'CL-S1': {"text": 'Output tables are structurally consistent with the supplied FAA/GFF3.', "source": 'references/provenance.md', "anchor": 'permits structural review without usable execution evidence', "scope": COMMANDS},
 'CL-A1': {"text": 'Execution is operationally attested by a bound stage-status record.', "source": 'PROVENANCE.md', "anchor": 'not cryptographic proof against deliberate fabrication', "scope": COMMANDS},
 'CL-A2': {"text": 'Results are structurally valid; execution is unattested.', "source": 'SKILL.md', "anchor": 'structurally valid, execution-unattested', "scope": COMMANDS},
 'CL-D1': {"text": 'The database cache matches the preserved expected manifest.', "source": 'references/provenance.md', "anchor": 'every expected path and digest', "scope": COMMANDS},
 'CL-O1': {"text": 'The overlay is a derived comparison; native tables are unchanged.', "source": 'references/reporting.md', "anchor": 'An exact-category CGC overlay is a derived comparison', "scope": COMMANDS},
 'CL-C1': {"text": 'Circular windows were audited against original GFF3 topology.', "source": 'references/reporting.md', "anchor": 'use original GFF3 topology and sequence-region lengths', "scope": COMMANDS},
 'CL-N0': {"text": 'Any assessment or validation was performed.', "source": 'SKILL.md', "anchor": 'Make decisions from', "scope": COMMANDS},
 'CL-N1': {"text": 'The run completed successfully or the pipeline executed.', "source": 'SKILL.md', "anchor": 'File presence or declared success is insufficient.', "scope": COMMANDS - {'describe','verify-db','prepare','cgc-overlay','audit-circular'}},
 'CL-N2': {"text": 'The database was verified.', "source": 'references/provenance.md', "anchor": 'does not establish that absent bytes were verified', "scope": COMMANDS},
 'CL-N3': {"text": 'The three methods independently confirm a family; they share CAZy-derived information.', "source": 'references/reporting.md', "anchor": 'The methods share CAZy-derived information', "scope": COMMANDS},
 'CL-N4': {"text": 'A DIAMOND family on a reference protein proves the query has that domain.', "source": 'references/reporting.md', "anchor": 'not query-domain evidence by itself', "scope": COMMANDS},
 'CL-N5': {"text": 'A dbCAN-sub _e<number> group is a curated CAZy subfamily.', "source": 'references/reporting.md', "anchor": 'must not be described as a curated CAZy subfamily', "scope": COMMANDS},
 'CL-N6': {"text": 'Substrate or PUL matches demonstrate substrate utilisation or activity.', "source": 'references/reporting.md', "anchor": 'experimentally demonstrated activity', "scope": COMMANDS},
 'CL-N7': {"text": 'Bitscore sums are probabilities.', "source": 'references/reporting.md', "anchor": 'bitscore sums are not probabilities', "scope": COMMANDS},
 'CL-N8': {"text": 'The overlay is an upstream package patch.', "source": 'SKILL.md', "anchor": 'upstream package patch', "scope": COMMANDS},
 'CL-N9': {"text": 'The sample label verifies isolate identity.', "source": 'SKILL.md', "anchor": 'verifies isolate identity', "scope": COMMANDS},
 'CL-N10': {"text": 'The attestation is cryptographic or tamper-proof.', "source": 'PROVENANCE.md', "anchor": 'Operational evidence, not tamper-proof proof.', "scope": COMMANDS},
 'CL-N11': {"text": 'GH0/GT0 or other zero-root labels are resolved families.', "source": 'SKILL.md', "anchor": 'outside resolved-family counts', "scope": COMMANDS},
}

def derive_claims(command, outcome, evidence, result):
    result = result or {}
    may, forbidden = set(), set()
    ok = outcome['kind'] == 'ok'
    if outcome['kind'] in {'refused', 'failed', 'usage', 'error'}: forbidden.add('CL-N0')
    if evidence['attestation'] != 'attested': forbidden.add('CL-N1')
    elif ok:
        may.add('CL-A1'); forbidden.add('CL-N10')
    if ok and evidence['structure'] == 'valid':
        if command in {'validate', 'summarize'}: may.add('CL-S1')
        if evidence['attestation'] == 'unattested': may.add('CL-A2')
    if command == 'preflight':
        checks = result.get('checks') or []
        if ok and result.get('ready') is True and checks and all(row['state']=='pass' for row in checks): may.add('CL-P1')
        if outcome['kind']=='negative' and outcome.get('code')=='PREFLIGHT_UNMET' and checks and any(row['state'] in {'fail','skipped'} for row in checks): may.add('CL-P2')
    facts = {'expected_file_count': result.get('expected_file_count'),
             'expected_manifest_sha256': result.get('expected_manifest_sha256')}
    valid_facts = (type(facts['expected_file_count']) is int and facts['expected_file_count']>=0
        and isinstance(facts['expected_manifest_sha256'],str)
        and re.fullmatch(r'[0-9a-f]{64}',facts['expected_manifest_sha256']) is not None)
    if command == 'verify-db':
        if ok and result.get('match') is True:
            if valid_facts: may.add('CL-D1')
        else: forbidden.add('CL-N2')
    if command == 'summarize':
        forbidden.update('CL-N%d' % n for n in (3, 4, 5, 6, 11))
        if result.get('substrate_rows', 0) > 0: forbidden.add('CL-N7')
    if command == 'cgc-overlay':
        forbidden.add('CL-N8')
        if ok: may.add('CL-O1')
    if command == 'audit-circular' and ok: may.add('CL-C1')
    if result.get('sample_source') == 'faa_stem': forbidden.add('CL-N9')
    def render(ids):
        rows = [{'id': key, 'text': CLAIMS[key]['text'], 'source': CLAIMS[key]['source'], 'anchor': CLAIMS[key]['anchor']}
                for key in sorted(ids) if command in CLAIMS[key]['scope']]
        for row in rows:
            if row['id']=='CL-D1': row['facts']=facts
        return rows
    return {'may_say': render(may), 'may_not_say': render(forbidden)}
