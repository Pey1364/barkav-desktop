"""Show only the test failures that are new compared with a known baseline.

Run pytest with -rfE, save its output, then compare:

    cd app
    python -m pytest tests/test_data_entry_gaps187.py -q -rfE > run.log 2>&1
    python tools/test_baseline187.py run.log

The baseline is tests/known_failures187.txt (one test id per line, '#' starts a comment).
Exit code 0: no new failure. Exit code 1: at least one new failure, listed on stdout.
Failures that are in the baseline are counted but not listed, so the output stays short.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = APP / 'tests' / 'known_failures187.txt'
# pytest prints "FAILED <test id> - <reason>" in -rf/-rfE summaries; the reason is optional.
SUMMARY = re.compile(r'^(?:FAILED|ERROR) (.+?)(?: - .*)?$')


def failures_in(text: str) -> set[str]:
    found = set()
    for line in text.splitlines():
        match = SUMMARY.match(line.strip())
        if match:
            found.add(match.group(1).strip())
    return found


def baseline_in(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')}


def compare(run_text: str, baseline_text: str) -> tuple[list[str], int]:
    """(new failures, number of known failures seen in this run)."""
    run, known = failures_in(run_text), baseline_in(baseline_text)
    new = sorted(run - known)
    return new, len(run & known)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('log', type=Path, help='pytest output saved with -rfE')
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    run_text = args.log.read_text(encoding='utf-8', errors='replace')
    baseline_text = args.baseline.read_text(encoding='utf-8')
    new, known_seen = compare(run_text, baseline_text)
    if not new and not known_seen and 'passed' not in run_text and 'failed' not in run_text:
        print('no pytest summary found in the log; did the run finish?', file=sys.stderr)
        return 2
    for test_id in new:
        print(f'NEW  {test_id}')
    print(f'{len(new)} new failure(s); {known_seen} known failure(s) seen again')
    return 1 if new else 0


if __name__ == '__main__':
    sys.exit(main())
