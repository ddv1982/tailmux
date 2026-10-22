#!/usr/bin/env python3
"""Select real acceptance evidence or the finite exact-source live-only exception."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from package import ReleaseRequest
from preflight import live_waiver, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--waiver-sha256', required=True)
    args = parser.parse_args()
    try:
        request = ReleaseRequest(args.tag, args.source_sha)
        raw = os.environ.get('RELEASE_LIVE_ONLY_WAIVER', '')
        require(live_waiver(raw, request) == args.waiver_sha256, 'Waiver changed after approval')
        if raw:
            print(f'Live acceptance NOT_VERIFIED. Owner-authorized live-only exception for {request.tag} at {request.source_sha}.')
            return 0
        gate = Path(__file__).resolve().parents[1] / 'acceptance/release_gate.py'
        return subprocess.run([sys.executable, str(gate), '--expected-sha', request.source_sha,
                               '--expected-merge-base', request.source_sha], check=False).returncode
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f'Release acceptance selection rejected: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
