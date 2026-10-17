#!/usr/bin/env python3
"""Refresh or check the complete portable skill's SHA256 inventory."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest_text(root):
    rows = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or '__pycache__' in relative.parts or '.git' in relative.parts:
            continue
        if relative.as_posix() == 'FILES.sha256' or path.suffix in {'.pyc', '.tmp'}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append('%s  %s\n' % (digest, relative.as_posix()))
    return ''.join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='fail on stale, missing or extra inventory entries')
    args = parser.parse_args()
    target = ROOT/'FILES.sha256'
    expected = manifest_text(ROOT)
    if args.check:
        if not target.exists() or target.read_text() != expected:
            parser.exit(1, 'FILES.sha256 is stale; run tools/refresh_files_sha256.py\n')
    else:
        target.write_text(expected)

if __name__ == '__main__': main()
