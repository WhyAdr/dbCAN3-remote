#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${DBCAN_PYTHON:-}" ]]; then
  printf '%s\n' 'Set DBCAN_PYTHON to the selected environment interpreter.' >&2
  printf '%s\n' "Usage: DBCAN_PYTHON=/path/to/env/bin/python $0 run --input-dir ..." >&2
  exit 2
fi
if [[ "$#" -eq 0 ]]; then
  printf '%s\n' 'Usage: run_dbcan_workflow.sh <prepare|validate|summarize|verify-db|preflight|run> [options]' >&2
  exit 2
fi
if [[ ! -x "$DBCAN_PYTHON" ]]; then
  printf 'DBCAN_PYTHON is not executable: %s\n' "$DBCAN_PYTHON" >&2
  exit 2
fi

exec "$DBCAN_PYTHON" "$script_dir/dbcan_workflow.py" "$@"
