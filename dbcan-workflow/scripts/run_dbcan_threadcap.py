#!/usr/bin/env python3
"""Invoke run_dbcan 5.2.9 with an explicit CPU-count cap for CLI gaps.

In 5.2.9, substrate_prediction has no --threads CLI option; its internal
default is os.cpu_count(). This version-guarded entry-point wrapper makes that
default equal the requested allocation. Other commands should use their native
--threads option. Unknown package versions fail closed.
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
from typing import Callable


SUPPORTED_VERSION = "5.2.9"


def cap_os_cpu_count(budget: int) -> Callable[[], int] | None:
    if budget < 1:
        raise ValueError("CPU budget must be positive")
    original = os.cpu_count
    os.cpu_count = lambda: budget  # scoped to this one CLI process
    return original


def main(argv: list[str] | None = None, *, version: str | None = None, entrypoint_loader=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or not args[0].isdigit():
        raise SystemExit("usage: run_dbcan_threadcap.py THREADS <run_dbcan subcommand and options>")
    budget = int(args.pop(0))
    if budget < 1:
        raise SystemExit("THREADS must be a positive integer")
    if version is None:
        try:
            version = importlib.metadata.version("dbcan")
        except importlib.metadata.PackageNotFoundError as exc:
            raise SystemExit("dbcan is not installed in the selected Python environment") from exc
    if version != SUPPORTED_VERSION:
        raise SystemExit(f"CPU-count compatibility wrapper is tested only for dbcan {SUPPORTED_VERSION}; found {version}")
    if not args:
        raise SystemExit("a run_dbcan subcommand is required")
    if "--threads" in args:
        raise SystemExit("use a native --threads option instead of the compatibility wrapper when available")
    if entrypoint_loader is None:
        candidates = [ep for ep in importlib.metadata.entry_points(group="console_scripts") if ep.name == "run_dbcan"]
        if len(candidates) != 1:
            raise SystemExit(f"expected one run_dbcan console entry point, found {len(candidates)}")
        entrypoint_loader = candidates[0].load
    old_argv = sys.argv[:]
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    old_env = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ[name] = str(budget)
    original = cap_os_cpu_count(budget)
    sys.argv = ["run_dbcan", *args]
    try:
        entrypoint = entrypoint_loader()
        result = entrypoint()
        return int(result) if isinstance(result, int) else 0
    finally:
        if original is not None:
            os.cpu_count = original
        sys.argv = old_argv
        for name, value in old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    raise SystemExit(main())
