#!/usr/bin/env python3
"""Validate evidence structure and bytes. This tool cannot approve a release."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

SCENARIOS = (
    'attach-create', 'missing-tmux', 'backend-state', 'invalid-snapshot',
    'duplicate-identity', 'shared-ipv6-dns', 'denied-policy', 'host-keys',
    'terminal-lifecycle', 'install-recovery',
)
PLATFORMS = ('linux-linux', 'macos-linux', 'linux-macos')
GATES = ('unit-static', 'performance', 'audit-security', 'audit-release', 'operator-review')
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
SECRET = re.compile(rb'tskey-[a-z]+-[A-Za-z0-9_-]+|gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:authorization|authkey|access_token|password|secret)\s*[=:]\s*["\']?(?!\[REDACTED\])[^\s"\']{6,}', re.I)


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def record(value, fields):
    require(type(value) is dict and set(value) == set(fields.split()), 'invalid record fields')
    return value


def text(value):
    require(type(value) is str and 0 < len(value) <= 4096 and
            not any(ord(c) < 32 or ord(c) == 127 for c in value), 'invalid text')
    return value


def sha(value, length=40):
    require(type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value), 'invalid digest')
    return value


def timestamp(value):
    text(value)
    require(value.endswith('Z'), 'UTC timestamp required')
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise Invalid('invalid timestamp') from exc
    require(parsed <= datetime.now(timezone.utc), 'future timestamp')
    return parsed


def clean_bytes(data):
    require(not SECRET.search(data), 'redaction gate rejected possible secret')


def read_regular(path, limit):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                0 < info.st_size <= limit, 'file type, link count, or size refused')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        require(len(data) <= limit, 'file too large')
        clean_bytes(data)
        return data
    finally:
        os.close(fd)


def json_bytes(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, 'invalid JSON constant'))
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise Invalid('invalid JSON document') from exc


def json_file(path):
    return json_bytes(read_regular(path, 1024 * 1024))


def load_request(path, expected_sha, expected_merge_base):
    value = record(json_file(path), 'schema source_sha merge_base_sha approved_by approved_at platforms')
    require(type(value['schema']) is int and value['schema'] == 1, 'unsupported schema')
    require(sha(value['source_sha']) == sha(expected_sha), 'request source SHA mismatch')
    require(sha(value['merge_base_sha']) == sha(expected_merge_base), 'request merge base mismatch')
    text(value['approved_by'])
    timestamp(value['approved_at'])
    require(type(value['platforms']) is dict and set(value['platforms']) == set(PLATFORMS),
            'all required platform pairs must be approved')
    for target in value['platforms'].values():
        record(target, 'target user isolated scope')
        require(target['isolated'] is True and target['scope'] == 'disposable-acceptance',
                'disposable isolated scope required')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:_-]{0,252}', text(target['target'])),
                'invalid approved target')
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,31}', text(target['user'])),
                'invalid approved user')
        require(target['user'] != 'root', 'nonroot approved user required')
    return value


def verify(bundle, request):
    root = Path(bundle).absolute()
    require(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
            'bundle directory refused')
    manifest_bytes = read_regular(root / 'evidence.json', 1024 * 1024)
    manifest = record(json_bytes(manifest_bytes),
                      'schema source_sha merge_base_sha origin redaction files scenarios gates')
    require(type(manifest['schema']) is int and manifest['schema'] == 1, 'unsupported schema')
    for key in ('source_sha', 'merge_base_sha'):
        require(sha(manifest[key]) == request[key], key + ' mismatch')
    origin = record(manifest['origin'], 'kind operator custody_ref')
    require(origin['kind'] == 'protected-operator', 'protected operator origin required')
    text(origin['operator'])
    text(origin['custody_ref'])
    redaction = record(manifest['redaction'], 'reviewer reviewed_at status')
    require(redaction['status'] == 'PASS', 'redaction review missing')
    text(redaction['reviewer'])
    timestamp(redaction['reviewed_at'])
    files = manifest['files']
    require(type(files) is list and 0 < len(files) <= 256, 'invalid evidence file count')
    indexed, total = {}, 0
    for entry in files:
        record(entry, 'path sha256 kind')
        name = text(entry['path'])
        relative = PurePosixPath(name)
        require(len(name) <= 1024 and len(relative.parts) <= 16 and not relative.is_absolute() and '..' not in relative.parts and
                str(relative) == name and '\\' not in name and name != 'evidence.json',
                'unsafe evidence path')
        require(name not in indexed, 'duplicate evidence path')
        require(entry['kind'] in ('text', 'native-screenshot', 'native-video'), 'invalid file kind')
        data = read_regular(root / name, MAX_FILE)
        total += len(data)
        require(total <= MAX_TOTAL, 'bundle too large')
        require(hashlib.sha256(data).hexdigest() == sha(entry['sha256'], 64), 'evidence digest mismatch')
        if entry['kind'] == 'text':
            try:
                decoded = data.decode('utf-8')
            except UnicodeError as exc:
                raise Invalid('text evidence must be UTF-8') from exc
            require('\x00' not in decoded, 'NUL in text evidence')
        elif entry['kind'] == 'native-screenshot':
            require(data.startswith(b'\x89PNG\r\n\x1a\n'), 'PNG evidence required')
        else:
            require(len(data) >= 12 and data[4:8] == b'ftyp', 'MP4 evidence required')
        indexed[name] = entry['kind']
    actual = set()
    allowed_dirs = {str(parent) for name in indexed for parent in PurePosixPath(name).parents if str(parent) != '.'}
    require(len(allowed_dirs) <= 256, 'too many evidence directories')
    def walk_error(_error):
        raise Invalid('unreadable evidence directory')
    for parent, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        for name in dirs:
            directory = Path(parent) / name
            require(not directory.is_symlink(), 'symlink directory refused')
            require(directory.relative_to(root).as_posix() in allowed_dirs, 'unlisted directory')
        for name in names:
            actual.add((Path(parent) / name).relative_to(root).as_posix())
            require(len(actual) <= 257, 'too many bundle members')
    require(actual == set(indexed) | {'evidence.json'}, 'unlisted or missing bundle file')

    def refs(values, kinds=('text',)):
        require(type(values) is list and 0 < len(values) <= 256 and
                len(set(values)) == len(values), 'invalid evidence references')
        require(all(type(v) is str and v in indexed for v in values), 'unknown evidence reference')
        require(set(indexed[v] for v in values) >= set(kinds), 'missing evidence kind')

    scenarios = manifest['scenarios']
    require(type(scenarios) is list and len(scenarios) == len(PLATFORMS) * len(SCENARIOS),
            'missing platform or scenario lanes')
    seen = set()
    for lane in scenarios:
        record(lane, 'platform scenario target user source_sha merge_base_sha status started_at finished_at inventory commands expected observed evidence operator_review')
        key = (lane['platform'], lane['scenario'])
        require(key[0] in PLATFORMS and key[1] in SCENARIOS and key not in seen,
                'unknown or duplicate lane')
        seen.add(key)
        approved = request['platforms'][key[0]]
        require(lane['target'] == approved['target'] and lane['user'] == approved['user'],
                'unapproved target or user')
        for field in ('source_sha', 'merge_base_sha'):
            require(lane[field] == request[field], 'stale lane SHA')
        require(lane['status'] == 'PASS', 'failed, skipped, or inconclusive lane')
        started, finished = timestamp(lane['started_at']), timestamp(lane['finished_at'])
        require(timestamp(request['approved_at']) <= started <= finished, 'invalid lane time order')
        inventory = record(lane['inventory'], 'client_os destination_os bash jq openssh tailscale_cli tailscale_daemon tmux vendor_patch policy_fixture')
        require(all(text(v) for v in inventory.values()), 'incomplete inventory')
        client_os, destination_os = key[0].split('-')
        require(inventory['client_os'].startswith(client_os + ' ') and
                inventory['destination_os'].startswith(destination_os + ' '), 'platform inventory mismatch')
        require(type(lane['commands']) is list and 0 < len(lane['commands']) <= 64, 'missing commands')
        for command in lane['commands']:
            record(command, 'argv expected_exit exit_code outcome transcript')
            require(type(command['argv']) is list and 0 < len(command['argv']) <= 64,
                    'command argv required')
            for arg in command['argv']:
                text(arg)
            require(type(command['exit_code']) is int and type(command['expected_exit']) is int and
                    -255 <= command['exit_code'] <= 255 and
                    command['exit_code'] == command['expected_exit'] and command['outcome'] == 'exited',
                    'command failed, cancelled, or inconclusive')
            require(indexed.get(command['transcript']) == 'text', 'command transcript required')
        text(lane['expected'])
        text(lane['observed'])
        refs(lane['evidence'], ('text', 'native-screenshot', 'native-video'))
        review = record(lane['operator_review'], 'reviewer source_sha reviewed_at status receipt')
        require(review['source_sha'] == request['source_sha'] and review['status'] == 'PASS',
                'operator review incomplete')
        text(review['reviewer'])
        require(timestamp(review['reviewed_at']) >= finished, 'review predates lane')
        require(indexed.get(review['receipt']) == 'text', 'operator receipt required')
    gates = manifest['gates']
    require(type(gates) is dict and set(gates) == set(GATES), 'missing release gate lane')
    for gate in gates.values():
        record(gate, 'status source_sha reviewer reviewed_at evidence')
        require(gate['status'] == 'PASS' and gate['source_sha'] == request['source_sha'],
                'gate incomplete or stale')
        text(gate['reviewer'])
        timestamp(gate['reviewed_at'])
        refs(gate['evidence'])
    return {'structure': 'COMPLETE', 'verdict': 'NOT_VERIFIED', 'source_sha': request['source_sha'],
            'merge_base_sha': request['merge_base_sha'], 'platform_pairs': list(PLATFORMS),
            'scenario_count': len(seen), 'trust': 'operator origin and truth require independent protected review',
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'request_sha256': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--expected-merge-base', required=True)
    args = parser.parse_args()
    try:
        request = load_request(args.request, args.expected_sha, args.expected_merge_base)
        result = verify(args.bundle, request)
        result['request_sha256'] = hashlib.sha256(read_regular(args.request, 1024 * 1024)).hexdigest()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Invalid, OSError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({'structure': 'REJECTED', 'verdict': 'NOT_VERIFIED',
                          'reason': str(exc) if isinstance(exc, Invalid) else 'invalid or unreadable evidence'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
