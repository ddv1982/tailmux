#!/usr/bin/env python3
"""Check protected operator evidence expectations. Emit structural results only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import zipfile

from unpack import unpack
from verify import MAX_TOTAL, load_request, read_regular, require, sha, verify

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'ddv1982/tailmux'


def gate(expected_sha, expected_merge_base):
    sha(expected_sha)
    sha(expected_merge_base)
    source = os.environ.get('ACCEPTANCE_SOURCE_SHA', '')
    artifact = os.environ.get('ACCEPTANCE_ARTIFACT_ID', '')
    archive_digest = os.environ.get('ACCEPTANCE_ARCHIVE_SHA256', '')
    request_digest = os.environ.get('ACCEPTANCE_REQUEST_SHA256', '')
    require(sha(source) == expected_sha, 'protected acceptance source mismatch')
    require(re.fullmatch('[1-9][0-9]{0,19}', artifact), 'invalid protected artifact ID')
    sha(archive_digest, 64)
    sha(request_digest, 64)
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY and
            os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'protected hosted repository job required')
    require(os.environ.get('GITHUB_SHA') == expected_sha and
            os.environ.get('GITHUB_WORKFLOW_SHA') == expected_sha, 'job source identity mismatch')
    for args, expected in ((('rev-parse', 'HEAD'), expected_sha),
                           (('merge-base', 'HEAD', 'origin/main'), expected_merge_base)):
        actual = subprocess.check_output(['git', '-C', str(ROOT), *args], timeout=5, stderr=subprocess.DEVNULL)
        require(actual.decode().strip() == expected, 'checkout source or merge base mismatch')
    subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', 'HEAD', '--'], check=True,
                   timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix='tailmux-acceptance-') as temporary:
        root = Path(temporary).resolve()
        archive = root / 'evidence.zip'
        def limit():
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_TOTAL, MAX_TOTAL))
        endpoint = 'repos/' + REPOSITORY + '/actions/artifacts/' + artifact + '/zip'
        with archive.open('xb') as output:
            subprocess.run(['gh', 'api', '--hostname', 'github.com', '--method', 'GET', endpoint],
                           stdout=output, stderr=subprocess.DEVNULL, check=True, timeout=120, preexec_fn=limit)
        unpack(archive, archive_digest, root / 'input')
        request_path = root / 'input/request.json'
        require(hashlib.sha256(read_regular(request_path, 1024 * 1024)).hexdigest() == request_digest,
                'protected request digest mismatch')
        request = load_request(request_path, expected_sha, expected_merge_base)
        result = verify(root / 'input/bundle', request)
        result.update(request_sha256=request_digest, archive_sha256=archive_digest, artifact_id=artifact)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--expected-merge-base', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(gate(args.expected_sha, args.expected_merge_base), sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RecursionError, subprocess.SubprocessError,
            zipfile.BadZipFile, NotImplementedError, RuntimeError):
        print('Acceptance release gate rejected. NOT VERIFIED.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
