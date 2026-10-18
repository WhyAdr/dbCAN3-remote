"""Durable sample event records and bounded diagnostic log excerpts."""
from __future__ import annotations

import json
import os
from dbcan_trust import sanitize_text, bounded_details
from datetime import datetime, timezone
from pathlib import Path

LOG_TAIL_BYTES = 8192
LOG_TAIL_LINES = 40


def append_event(path: Path, run_id: str, sample: str, stage: str | None,
                 event: str, **details) -> None:
    """Append one record; the runner owns one writer per fresh sample directory."""
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
              "run_id": run_id, "sample": sample, "stage": stage, "event": event}
    if details:
        record["details"] = bounded_details(details)
    payload = json.dumps(record, sort_keys=True, allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def failure_context(sample: str, stage: str, exit_code: int | None,
                    log_path: Path) -> dict:
    """Read at most 8193 source bytes, retain at most 40 lines / 8192 UTF-8 bytes."""
    context = {"sample": sample, "stage": stage, "exit_code": exit_code,
               "log_path": str(log_path.resolve()), "log_tail": "",
               "log_tail_truncated": False}
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - LOG_TAIL_BYTES - 1))
            raw = handle.read(LOG_TAIL_BYTES + 1)
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        excerpt = "".join(lines[-LOG_TAIL_LINES:])
        encoded = excerpt.encode("utf-8")
        context["log_tail_truncated"] = (
            size > LOG_TAIL_BYTES or len(lines) > LOG_TAIL_LINES
            or len(encoded) > LOG_TAIL_BYTES)
        if len(encoded) > LOG_TAIL_BYTES:
            excerpt = encoded[-LOG_TAIL_BYTES:].decode("utf-8", errors="ignore")
        context["log_tail"] = sanitize_text(excerpt, LOG_TAIL_BYTES)[0]
    except OSError:
        context["log_tail_error"] = "The stage log is unavailable or unreadable."
    return context
