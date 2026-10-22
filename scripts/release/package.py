#!/usr/bin/env python3
"""Build and authenticate the bounded tailmux portable package."""

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

REPOSITORY = "ddv1982/tailmux"
WORKFLOW = f"{REPOSITORY}/.github/workflows/release.yml"
MAX_COMPRESSED = 8 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
MAX_MANIFEST = 32 * 1024
MANIFEST = "manifest.json"
PAYLOAD = (
    "LICENSE", "README.md", "SECURITY.md", "VERSION", "bin/tailmux", "docs/acceptance.md",
    "docs/architecture.md", "docs/compatibility.md", "docs/dependencies.md", "docs/taildrive.md",
    "docs/releases.md", "docs/troubleshooting.md", "scripts/lib/cli.sh",
    "scripts/lib/install.sh", "scripts/lib/managed_blocks.sh", "scripts/lib/platform.sh",
    "scripts/lib/rc_blocks.sh", "scripts/lib/uninstall.sh", "setup.sh",
)
TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?", re.ASCII)
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)


@dataclass(frozen=True)
class ReleaseRequest:
    tag: str
    source_sha: str
    repository: str = REPOSITORY

    def __post_init__(self):
        if not TAG.fullmatch(self.tag) or not SHA.fullmatch(self.source_sha) or self.repository != REPOSITORY:
            raise ValueError("Expected a version tag, independent full source SHA, and fixed repository")


@dataclass(frozen=True)
class Manifest:
    request: ReleaseRequest
    members: dict

    def encode(self):
        return (json.dumps({"format": "tailmux-portable-v1", "version": self.request.tag[1:],
                            "source_sha": self.request.source_sha, "members": self.members},
                           sort_keys=True, separators=(",", ":")) + "\n").encode()


@dataclass(frozen=True)
class VerifiedRelease:
    request: ReleaseRequest
    archive: bytes


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def run(command, **kwargs):
    return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120, **kwargs).stdout


def git(root, *args):
    return run(["git", "-C", str(root), *args])


def header(path, size):
    info = tarfile.TarInfo(path)
    info.size = size
    info.mode = 0o755 if path == "bin/tailmux" else 0o644
    return info.tobuf(format=tarfile.USTAR_FORMAT, encoding="ascii", errors="strict")


def assemble(request, files):
    members = {path: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
               for path, data in files.items()}
    files = {MANIFEST: Manifest(request, members).encode(), **files}
    raw = io.BytesIO()
    for path in (MANIFEST, *PAYLOAD):
        data = files[path]
        if len(data) > (MAX_MANIFEST if path == MANIFEST else MAX_FILE):
            raise ValueError("Package member exceeds limit")
        raw.write(header(path, len(data)))
        raw.write(data)
        raw.write(b"\0" * (-len(data) % 512))
    raw.write(b"\0" * 1024)
    raw.write(b"\0" * (-raw.tell() % tarfile.RECORDSIZE))
    if raw.tell() > MAX_EXPANDED:
        raise ValueError("Expanded package exceeds limit")
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0, compresslevel=9) as stream:
        stream.write(raw.getvalue())
    if out.tell() > MAX_COMPRESSED:
        raise ValueError("Compressed package exceeds limit")
    return out.getvalue()


def build(root, request, destination):
    if git(root, "rev-parse", "HEAD").decode().strip() != request.source_sha:
        raise ValueError("Checkout is not the expected source")
    if git(root, "rev-parse", f"refs/tags/{request.tag}^{{commit}}").decode().strip() != request.source_sha:
        raise ValueError("Version tag is not the expected source")
    files = {}
    for path in PAYLOAD:
        entry = git(root, "ls-tree", request.source_sha, "--", path).decode().split()
        expected_mode = "100755" if path == "bin/tailmux" else "100644"
        if len(entry) != 4 or entry[0:2] != [expected_mode, "blob"] or entry[3] != path:
            raise ValueError(f"Missing or non-regular committed payload: {path}")
        size = int(git(root, "cat-file", "-s", entry[2]))
        if size > MAX_FILE:
            raise ValueError("Committed payload exceeds limit")
        files[path] = git(root, "cat-file", "blob", entry[2])
    if files["VERSION"] != (request.tag[1:] + "\n").encode():
        raise ValueError("VERSION does not match the requested tag")
    embedded = re.findall(rb"^(?:readonly )?TAILMUX_VERSION=([^\r\n]+)$", files["bin/tailmux"], re.MULTILINE)
    if embedded != [request.tag[1:].encode()]:
        raise ValueError("Embedded binary version does not match VERSION and tag")
    setup_version = re.findall(rb"^TAILMUX_VERSION=([^\r\n]+)$", files["setup.sh"], re.MULTILINE)
    if setup_version != embedded:
        raise ValueError("Installer version does not match binary version")
    archive = assemble(request, files)
    inspect(VerifiedRelease(request, archive))
    with destination.open("xb") as stream:
        stream.write(archive)


def authenticate(path, request):
    with path.open("rb") as stream:
        archive = stream.read(MAX_COMPRESSED + 1)
    if not archive or len(archive) > MAX_COMPRESSED:
        raise ValueError("Empty or oversized compressed package")
    with tempfile.TemporaryDirectory(prefix="tailmux-attestation-") as private:
        snapshot = Path(private) / "package.tar.gz"
        snapshot.write_bytes(archive)
        snapshot.chmod(0o600)
        run(["gh", "attestation", "verify", str(snapshot), "--repo", request.repository,
             "--signer-workflow", WORKFLOW, "--signer-digest", request.source_sha,
             "--source-ref", f"refs/tags/{request.tag}", "--source-digest", request.source_sha,
             "--deny-self-hosted-runners"],
            env={**os.environ, "GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1"})
    return VerifiedRelease(request, archive)


def inspect(verified):
    with gzip.GzipFile(fileobj=io.BytesIO(verified.archive)) as stream:
        raw = stream.read(MAX_EXPANDED + 1)
    if len(raw) > MAX_EXPANDED or len(raw) % tarfile.RECORDSIZE:
        raise ValueError("Invalid or oversized expanded package")
    files = {}
    offset = 0
    for expected in (MANIFEST, *PAYLOAD):
        block = raw[offset:offset + 512]
        info = tarfile.TarInfo.frombuf(block, encoding="ascii", errors="strict")
        limit = MAX_MANIFEST if expected == MANIFEST else MAX_FILE
        if (info.name != expected or info.type != tarfile.REGTYPE or not 0 <= info.size <= limit
                or block != header(expected, info.size)):
            raise ValueError("Noncanonical, unexpected, duplicate, or special archive member")
        offset += 512
        data = raw[offset:offset + info.size]
        padding = raw[offset + info.size:offset + info.size + (-info.size % 512)]
        if len(data) != info.size or padding != b"\0" * (-info.size % 512):
            raise ValueError("Truncated content or unexpected padding")
        files[expected] = data
        offset += info.size + (-info.size % 512)
    expected_length = ((offset + 1024 + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE
    if len(raw) != expected_length or any(raw[offset:]):
        raise ValueError("Missing terminator or unexpected archive content")
    manifest = json.loads(files[MANIFEST], object_pairs_hook=strict_object)
    members = {path: {"size": len(files[path]), "sha256": hashlib.sha256(files[path]).hexdigest()}
               for path in PAYLOAD}
    expected = Manifest(verified.request, members)
    if manifest != json.loads(expected.encode()) or files[MANIFEST] != expected.encode():
        raise ValueError("Manifest identity, members, sizes, or digests do not match")
    return files


def unpack(verified, parent):
    files = inspect(verified)
    parent = parent.resolve(strict=True)
    metadata = parent.stat()
    if not parent.is_dir() or metadata.st_uid != os.getuid() or metadata.st_mode & 0o022:
        raise ValueError("Output parent must be a current-user directory without shared write access")
    stage = Path(tempfile.mkdtemp(prefix="tailmux-verified-", dir=parent))
    try:
        for path, data in files.items():
            target = stage / path
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o755 if path == "bin/tailmux" else 0o644)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--tag", required=True)
        command.add_argument("--source-sha", required=True)
        if name == "build":
            command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("archive", type=Path)
            command.add_argument("--output-parent", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = ReleaseRequest(args.tag, args.source_sha)
        if args.command == "build":
            build(args.root, request, args.output)
            print(args.output)
        else:
            print(unpack(authenticate(args.archive, request), args.output_parent))
    except (ValueError, OSError, EOFError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Release rejected: {error}\n")


if __name__ == "__main__":
    main()
