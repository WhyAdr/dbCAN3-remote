"""Typed CLI outcomes and stable recovery registry (standard library only)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

EXIT_CODES = {'ok': 0, 'error': 1, 'usage': 2, 'refused': 3, 'negative': 4, 'failed': 5}

def remedy(id, text, flags=(), claim_effects=()):
    return {'id': id, 'text': text, 'flags': list(flags), 'claim_effects': list(claim_effects)}

def entry(kind, text, remedies=(), forbidden=()):
    return {'kind': kind, 'summary': text, 'remediation': list(remedies),
            'forbidden': [{'id': key, 'text': value} for key, value in forbidden]}

REGISTRY = {
 'OK': entry('ok', 'The requested operation completed.'),
 'USAGE_INVALID': entry('usage', 'The command line is invalid.'),
 'PATHS_OVERLAP': entry('refused', 'Output paths overlap protected paths or are not fresh.',
    [remedy('FRESH_PATHS', 'Choose fresh, disjoint output roots.')],
    [('NO_PROTECTED_OUTPUTS', 'Do not reuse inputs, native results, environment or database directories as outputs.')]),
 'ATTESTATION_REQUIRED': entry('refused', 'Strict validation requires a bound stage-status manifest.',
    [remedy('PASS_STATUS_FILE', "Pass the run's stage_status.json.", ['--status-file']),
     remedy('STRUCTURAL_REVIEW_ONLY', 'Use structural review only; do not claim execution.', ['--allow-unattested'], ['CL-N1'])],
    [('NO_FABRICATED_MANIFEST', 'Do not create or edit a manifest to satisfy this check.')]),
 'ATTESTATION_REJECTED': entry('refused', 'The supplied stage-status manifest was rejected.',
    [remedy('PRESERVE_REJECTION', 'Report and preserve the rejection. Supply a different bound manifest.', ['--status-file']),
     remedy('STRUCTURAL_REVIEW_ONLY', 'Omit the rejected manifest and request structural review; retain the rejection in the report.', ['--allow-unattested'], ['CL-N1'])],
    [('NO_EDITED_MANIFEST', 'Do not edit the rejected manifest to make it pass.')]),
 'RESULTS_DIR_MISSING': entry('refused', 'The selected native results directory is missing.',
    [remedy('SELECT_RESULTS', 'Supply the exact existing native results directory.', ['--results-dir'])],
    [('NO_EMPTY_SUBSTITUTE', 'Do not create an empty directory to satisfy this check.')]),
 'INPUT_MISSING': entry('refused', 'A required input file or directory is missing.',
    [remedy('SELECT_INPUTS', 'Supply the existing input paths.')]),
 'INPUT_MISMATCH': entry('refused', 'The selected FAA/GFF3 identities do not match.',
    [remedy('MATCHED_PAIR', 'Supply the matching FAA/GFF3 pair.', ['--faa', '--gff'])]),
 'SAMPLE_ID_UNSAFE': entry('refused', 'Sample names must be safe and unique.',
    [remedy('SAFE_NAMES', 'Use distinct plain isolate names without path traversal.', ['--samples'])]),
 'ENV_UNMET': entry('refused', 'The pinned runtime requirements are unmet.',
    [remedy('PROVISION_ENV', 'Provision the selected pinned environment and DIAMOND 2.2.8.', ['--env-dir'])],
    [('NO_AUTOINSTALL', 'Do not install or download without user confirmation.')]),
 'DB_UNVERIFIED': entry('refused', 'The database is unavailable or unverified.',
    [remedy('VERIFY_CACHE', 'Run verify-db on a supplied cache and preserved manifest.', ['--db-dir', '--expected-manifest'])],
    [('NO_AUTODOWNLOAD', 'Do not download databases without explicit user confirmation.')]),
 'THREADS_EXCEED_ALLOCATION': entry('refused', 'Requested threads exceed the detected CPU allocation.',
    [remedy('LOWER_THREADS', 'Lower the thread budget to the detected allocation.', ['--threads'])]),
 'MANIFEST_PATH_UNSAFE': entry('refused', 'The expected checksum manifest is unsafe or malformed.',
    [remedy('PRESERVED_MANIFEST', 'Use the preserved checksum manifest.', ['--expected-manifest'])]),
 'VERSION_UNSUPPORTED': entry('refused', 'The requested compatibility version is unsupported.',
    [remedy('COMPATIBLE_VERSION', 'Use the overlay only for corroborated dbCAN 5.2.9 results.', ['--dbcan-version'])]),
 'STRUCTURE_INVALID': entry('negative', 'The supplied data are structurally inconsistent.'),
 'DB_MISMATCH': entry('negative', 'The cache does not match the expected manifest.'),
 'STAGE_FAILED': entry('failed', 'An external stage failed; inspect its log and rerun into fresh directories.'),
 'INTERNAL_ERROR': entry('error', 'An unexpected tool defect occurred; report the stderr traceback.'),
}

class WorkflowOutcome(Exception):
    def __init__(self, code, message, *, details=None):
        super().__init__(message)
        self.code = code
        self.kind = REGISTRY[code]['kind']
        self.details = details or {}

class Refusal(WorkflowOutcome, ValueError):
    pass

class MissingPathRefusal(Refusal, FileNotFoundError):
    pass

class ExistingPathRefusal(Refusal, FileExistsError):
    pass

class RuntimeRefusal(Refusal, RuntimeError):
    pass

class NegativeResult(WorkflowOutcome, ValueError):
    pass

class MissingDataResult(NegativeResult, FileNotFoundError):
    pass

class StageFailure(WorkflowOutcome, RuntimeError):
    pass

class UsageError(WorkflowOutcome):
    pass

@dataclass
class CommandResult:
    kind: str = 'ok'
    code: str = 'OK'
    summary: str = 'The requested operation completed.'
    result: Any = None
    evidence: dict = field(default_factory=lambda: {'structure': 'not_assessed', 'attestation': 'not_applicable'})
    artifacts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    refusal: Any = None
    run_id: Any = None

    @classmethod
    def from_exception(cls, exc):
        cr = cls(kind=exc.kind, code=exc.code, summary=str(exc))
        if exc.kind == 'refused':
            info = REGISTRY[exc.code]
            cr.refusal = {'code': exc.code, 'message': str(exc),
                'remediation': info['remediation'], 'forbidden': info['forbidden'], 'details': exc.details}
            if exc.code == 'ATTESTATION_REJECTED':
                cr.evidence['attestation'] = 'rejected'
        elif exc.kind == 'negative':
            cr.evidence['structure'] = 'invalid'
            cr.findings.append({'code': exc.code, 'message': str(exc), 'location': None})
        return cr
