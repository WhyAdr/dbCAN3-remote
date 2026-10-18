"""Data-free decision fields and bounded, explicitly untrusted diagnostics."""
from __future__ import annotations
import json
import re

class TrustViolation(Exception):
    """An envelope crossed the trusted-text boundary."""

_ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])')
_CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
_FMT = re.compile('[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]')
WARNINGS_REGISTRY = {
 'SAMPLE_INFERRED': 'Sample label was inferred from the FAA filename stem.',
 'DEPRECATED_FLAG_JSON': '--json is deprecated; use --out-json.',
 'DEPRECATED_FLAG_TSV': '--tsv is deprecated; use --out-tsv.',
 'ENVELOPE_PERSIST_FAILED': 'The envelope could not be persisted; the operation outcome is unchanged.',
 'STATUS_UNREADABLE': 'Stage-status diagnostics could not be read.',
}
UNTRUSTED_PATHS = [
 '/run_id', '/diagnostics', '/refusal/details', '/artifacts/*/path', '/findings/*/location',
 '/warnings/*/location', '/result',
 # Persisted JSON records share these source-data paths with their envelope.
 '/failure/diagnostic', '/failure/log_tail', '/failure/log_path', '/failures',
 '/sample', '/samples', '/input_faa', '/input_gff', '/results_dir', '/metadata_dir',
 '/stages/*/argv', '/stages/*/log_file', '/stages/*/reason',
 '/details', '/validation', '/scientific_summary', '/sample_summaries', '/preflight',
]


def sanitize_text(value, limit=512):
    text = value if isinstance(value, str) else repr(value)
    text = text.encode('utf-8', 'replace').decode('utf-8')
    text = _ANSI.sub('', text)
    text = _CTRL.sub('', text)
    text = _FMT.sub('', text)
    truncated = len(text) > limit
    return text[:limit], truncated


def bounded_details(value, limit=512, max_items=16, _depth=0):
    """Bound diagnostic trees without converting structured numbers to text."""
    if _depth > 8: return '[depth limit]'
    if isinstance(value, str): return sanitize_text(value, limit)[0]
    if isinstance(value, dict):
        return {sanitize_text(k,limit)[0]: bounded_details(v,limit,max_items,_depth+1)
                for k,v in list(value.items())[:max_items]}
    if isinstance(value, (list,tuple)):
        rows=[bounded_details(v,limit,max_items,_depth+1) for v in value[:max_items]]
        if len(value)>max_items: rows.append('…(%d more)' % (len(value)-max_items))
        return rows
    if value is None or isinstance(value,(int,float,bool)):return value
    return sanitize_text(value,limit)[0]


def sanitize_data(value):
    """Sanitize display data without changing its numeric or container types."""
    if isinstance(value,str): return sanitize_text(value,8192)[0]
    if isinstance(value,dict):return {sanitize_text(k,512)[0]:sanitize_data(v) for k,v in value.items()}
    if isinstance(value,list):return [sanitize_data(v) for v in value]
    return value


def make_diagnostic(origin, text, *, ref=None):
    clean,cut=sanitize_text(text)
    return {'origin': origin, 'untrusted': True, 'text': clean, 'truncated': cut,
            'ref': sanitize_text(ref)[0] if ref is not None else None}


def bound_diagnostics(items, max_items=16, max_bytes=8192):
    bounded=[]
    total=len(items)
    for item in items[:max_items]:
        clean=make_diagnostic(item['origin'],item['text'],ref=item.get('ref'))
        clean['truncated'] = clean['truncated'] or bool(item.get('truncated'))
        if len(json.dumps(bounded+[clean],ensure_ascii=True).encode()) > max_bytes:break
        bounded.append(clean)
    return bounded,total,len(bounded)<total or any(x['truncated'] for x in bounded)


def assert_trusted(env, registry, warnings_registry):
    outcome=env['outcome']
    if outcome['code'] not in registry or outcome['summary'] != registry[outcome['code']]['summary']:
        raise TrustViolation('Outcome text is not registry-backed.')
    if env['refusal'] is not None:
        refusal=env['refusal'];info=registry.get(refusal['code'])
        if info is None or refusal['message']!=info['summary'] or refusal['remediation']!=info['remediation'] or refusal['forbidden']!=info['forbidden']:
            raise TrustViolation('Refusal text is not registry-backed.')
    for row in env['findings']:
        if row['code'] not in registry or row['message']!=registry[row['code']]['summary']:
            raise TrustViolation('Finding text is not registry-backed.')
    for row in env['warnings']:
        if row['code'] not in warnings_registry or row['message']!=warnings_registry[row['code']]:
            raise TrustViolation('Warning text is not registry-backed.')
    if env['trust']['untrusted_paths'] != UNTRUSTED_PATHS:
        raise TrustViolation('The untrusted-path declaration changed.')
    if any(item.get('untrusted') is not True for item in env['diagnostics']):
        raise TrustViolation('Diagnostics must be declared untrusted.')

    from dbcan_claims import CLAIMS
    for side in env['claims'].values():
        for row in side:
            info=CLAIMS.get(row['id'])
            if info is None or any(row.get(key)!=info[key] for key in ('text','source','anchor')):
                raise TrustViolation('Claim text is not registry-backed.')
            if row['id']=='CL-D1':
                facts=row.get('facts',{})
                if type(facts.get('expected_file_count')) is not int or facts['expected_file_count']<0 or not isinstance(facts.get('expected_manifest_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',facts['expected_manifest_sha256']):
                    raise TrustViolation('Database claim facts are invalid.')
