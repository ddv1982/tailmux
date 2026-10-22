#!/usr/bin/env python3
"""Unpack an independently approved evidence ZIP, never executable payloads."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

from verify import Invalid, MAX_FILE, MAX_TOTAL, require, sha


def unpack(archive, expected_sha256, output):
    archive = Path(archive).absolute()
    output = Path(output).absolute()
    require(not any(p.is_symlink() for p in (archive, *archive.parents, output, *output.parents)),
            'symlink refused')
    require(not output.exists(), 'output must be new')
    fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_TOTAL, 'archive size or type refused')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else None
        if digest is None:
            stream.seek(0)
            h = hashlib.sha256()
            for block in iter(lambda: stream.read(65536), b''):
                h.update(block)
            digest = h.hexdigest()
        require(digest == sha(expected_sha256, 64), 'archive digest mismatch')
        stream.seek(0)
        with zipfile.ZipFile(stream) as bundle:
            entries = bundle.infolist()
            require(0 < len(entries) <= 300, 'archive member count refused')
            seen, total = set(), 0
            for item in entries:
                name = item.filename.rstrip('/') if item.is_dir() else item.filename
                path = PurePosixPath(name)
                require(name and len(name) <= 1024 and len(path.parts) <= 16 and not path.is_absolute() and
                        '..' not in path.parts and str(path) == name and '\\' not in name and
                        '\x00' not in item.orig_filename and name not in seen, 'unsafe or duplicate ZIP path')
                require(path.parts[0] == 'bundle' or name == 'request.json', 'unexpected ZIP member')
                require(item.filename == name + ('/' if item.is_dir() else ''), 'noncanonical ZIP path')
                require(not item.is_dir() or item.file_size == 0, 'directory payload refused')
                mode = stat.S_IFMT(item.external_attr >> 16)
                require(mode in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG) and
                        not item.flag_bits & 1, 'links, special files, or encryption refused')
                require(item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'unsupported compression')
                require(0 <= item.file_size <= MAX_FILE, 'ZIP member too large')
                total += item.file_size
                require(total <= MAX_TOTAL, 'expanded ZIP too large')
                seen.add(name)
            require('request.json' in seen and 'bundle/evidence.json' in seen, 'missing bundle documents')
            os.umask(0o077)
            output.mkdir(mode=0o700)
            for item in entries:
                target = output / item.filename
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, target.open('xb') as destination:
                    remaining = MAX_FILE
                    while True:
                        block = source.read(min(65536, remaining + 1))
                        if not block:
                            break
                        remaining -= len(block)
                        require(remaining >= 0, 'expanded member too large')
                        destination.write(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        unpack(args.archive, args.expected_sha256, args.output)
        print('Evidence unpacked for structural validation only. NOT VERIFIED.')
        return 0
    except (Invalid, OSError, ValueError, zipfile.BadZipFile, NotImplementedError, RuntimeError):
        print('Evidence archive rejected. NOT VERIFIED.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
