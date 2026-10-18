"""Deterministic report claims derived solely from structured evidence."""
from __future__ import annotations

# IDs and wording are contract v1; source paths identify the documented rules.
CLAIMS = {
 'CL-P1': ('All required preflight checks passed at assessment time.', 'references/phase4-diagnostics.md'),
 'CL-P2': ('The readiness check report completed; failed or skipped requirements remain.', 'references/phase4-diagnostics.md'),
 'CL-S1': ('Output tables are structurally consistent with the supplied FAA/GFF3.', 'SKILL.md'),
 'CL-A1': ('Execution is operationally attested by a bound stage-status record.', 'references/provenance.md'),
 'CL-A2': ('Results are structurally valid; execution is unattested.', 'SKILL.md'),
 'CL-D1': ('The database cache matches the preserved expected manifest.', 'references/provenance.md'),
 'CL-O1': ('The overlay is a derived comparison; native tables are unchanged.', 'references/reporting.md'),
 'CL-C1': ('Circular windows were audited against original GFF3 topology.', 'references/reporting.md'),
 'CL-N0': ('Any assessment or validation was performed.', 'contract'),
 'CL-N1': ('The run completed successfully or the pipeline executed.', 'SKILL.md'),
 'CL-N2': ('The database was verified.', 'references/provenance.md'),
 'CL-N3': ('The three methods independently confirm a family; they share CAZy-derived information.', 'references/reporting.md'),
 'CL-N4': ('A DIAMOND family on a reference protein proves the query has that domain.', 'references/reporting.md'),
 'CL-N5': ('A dbCAN-sub _e<number> group is a curated CAZy subfamily.', 'references/reporting.md'),
 'CL-N6': ('Substrate or PUL matches demonstrate substrate utilisation or activity.', 'references/reporting.md'),
 'CL-N7': ('Bitscore sums are probabilities.', 'references/reporting.md'),
 'CL-N8': ('The overlay is an upstream package patch.', 'SKILL.md'),
 'CL-N9': ('The sample label verifies isolate identity.', 'SKILL.md'),
 'CL-N10': ('The attestation is cryptographic or tamper-proof.', 'references/provenance.md'),
 'CL-N11': ('GH0/GT0 or other zero-root labels are resolved families.', 'SKILL.md'),
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
    if command == 'verify-db':
        (may if ok and result.get('match') is True else forbidden).add('CL-D1' if ok and result.get('match') is True else 'CL-N2')
    if command == 'summarize':
        forbidden.update('CL-N%d' % n for n in (3, 4, 5, 6, 11))
        if result.get('substrate_rows', 0) > 0: forbidden.add('CL-N7')
    if command == 'cgc-overlay':
        forbidden.add('CL-N8')
        if ok: may.add('CL-O1')
    if command == 'audit-circular' and ok: may.add('CL-C1')
    if result.get('sample_source') == 'faa_stem': forbidden.add('CL-N9')
    def render(ids):
        rows = [{'id': key, 'text': CLAIMS[key][0], 'source': CLAIMS[key][1]} for key in sorted(ids)]
        return rows
    return {'may_say': render(may), 'may_not_say': render(forbidden)}
