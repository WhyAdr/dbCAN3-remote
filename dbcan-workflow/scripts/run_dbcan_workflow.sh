#!/usr/bin/env bash
set -euo pipefail

usage_envelope() {
  cat <<'JSON'
{"contract_version":1,"tool":{"name":"dbcan-workflow","version":"0.3.1"},"command":null,"run_id":null,"outcome":{"kind":"usage","code":"USAGE_INVALID","summary":"The command line is invalid."},"exit":{"code":2,"policy":"strict"},"evidence":{"structure":"not_assessed","attestation":"not_applicable"},"result":null,"refusal":null,"findings":[],"warnings":[],"artifacts":[],"claims":{"may_say":[],"may_not_say":[{"id":"CL-N0","text":"Any assessment or validation was performed.","source":"contract"},{"id":"CL-N1","text":"The run completed successfully or the pipeline executed.","source":"SKILL.md"}]},"diagnostics":[],"diagnostics_total":0,"diagnostics_truncated":false,"trust":{"untrusted_paths":["/run_id","/diagnostics","/refusal/details","/artifacts/*/path","/findings/*/location","/warnings/*/location","/result","/failure/diagnostic","/failure/log_tail","/failure/log_path","/failures","/sample","/samples","/input_faa","/input_gff","/results_dir","/metadata_dir","/stages/*/argv","/stages/*/log_file","/stages/*/reason","/details","/validation","/scientific_summary","/sample_summaries","/preflight"]}}
JSON
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${DBCAN_PYTHON:-}" ]]; then
  printf '%s\n' 'Set DBCAN_PYTHON to the selected environment interpreter.' >&2
  printf '%s\n' "Usage: DBCAN_PYTHON=/path/to/env/bin/python $0 run --input-dir ..." >&2
  usage_envelope
  exit 2
fi
if [[ "$#" -eq 0 ]]; then
  printf '%s\n' 'Usage: run_dbcan_workflow.sh <prepare|validate|summarize|verify-db|preflight|run|audit-circular|cgc-overlay|describe> [options]' >&2
  usage_envelope
  exit 2
fi
if [[ ! -x "$DBCAN_PYTHON" ]]; then
  printf 'DBCAN_PYTHON is not executable: %s\n' "$DBCAN_PYTHON" >&2
  usage_envelope
  exit 2
fi

exec "$DBCAN_PYTHON" "$script_dir/dbcan_workflow.py" "$@"
