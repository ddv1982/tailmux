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
import platform
import re
import resource
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPOSITORY = "ddv1982/tailmux"
WORKFLOW = f"{REPOSITORY}/.github/workflows/release.yml"


@dataclass(frozen=True)
class PublisherIdentity:
    repository: str = REPOSITORY
    workflow: str = WORKFLOW
    repository_id: str = "1144643418"
    owner_id: str = "240215896"


PUBLISHER = PublisherIdentity()
MAX_INSTALLER = 1024 * 1024
MAX_BUNDLE = 2 * 1024 * 1024
MAX_VERIFICATION = 1024 * 1024
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
class InstallRequest:
    release: ReleaseRequest
    prefix: Path | None
    bundle: Path | None

    def __post_init__(self):
        if self.prefix is not None and (not self.prefix.is_absolute() or "\n" in str(self.prefix)
                                        or ".." in self.prefix.parts):
            raise ValueError("Install prefix must be an absolute path without traversal or newlines")


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


def bounded_read(path, limit):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError("Empty or oversized input")
    return data


def check_publisher(verification_json, expected=PUBLISHER):
    if not verification_json or len(verification_json) > MAX_VERIFICATION:
        raise ValueError("Empty or oversized verifier result")
    results = json.loads(verification_json, object_pairs_hook=strict_object)
    if type(results) is not list or not results:
        raise ValueError("Verifier must return a nonempty result array")
    for result in results:
        try:
            certificate = result["verificationResult"]["signature"]["certificate"]
            if (type(certificate) is not dict
                    or certificate.get("sourceRepositoryIdentifier") != expected.repository_id
                    or certificate.get("sourceRepositoryOwnerIdentifier") != expected.owner_id):
                raise ValueError("Verified certificate publisher IDs do not match")
        except (KeyError, TypeError) as error:
            raise ValueError("Verified certificate publisher IDs missing") from error


def authenticate(path, request, *, bundle=None):
    archive = bounded_read(path, MAX_COMPRESSED)
    bundle_bytes = bounded_read(bundle, MAX_BUNDLE) if bundle is not None else None
    with tempfile.TemporaryDirectory(prefix="tailmux-attestation-") as private:
        snapshot = Path(private) / "package.tar.gz"
        snapshot.write_bytes(archive)
        snapshot.chmod(0o600)
        command = ["gh", "attestation", "verify", str(snapshot), "--hostname", "github.com",
                   "--repo", request.repository, "--signer-workflow", PUBLISHER.workflow,
                   "--signer-digest", request.source_sha, "--source-ref", f"refs/tags/{request.tag}",
                   "--source-digest", request.source_sha, "--deny-self-hosted-runners", "--format", "json"]
        if bundle_bytes is not None:
            bundle_snapshot = Path(private) / "bundle.json"
            bundle_snapshot.write_bytes(bundle_bytes)
            bundle_snapshot.chmod(0o600)
            command += ["--bundle", str(bundle_snapshot)]
        output = Path(private) / "verified.json"
        with output.open("xb") as stream:
            subprocess.run(command, check=True, stdout=stream, stderr=subprocess.DEVNULL, timeout=120,
                           preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE,
                                                                (MAX_VERIFICATION, MAX_VERIFICATION)),
                           env={**os.environ, "GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1"})
        check_publisher(bounded_read(output, MAX_VERIFICATION))
    return VerifiedRelease(request, archive)


def download(request, name, destination, limit):
    url = f"https://github.com/{PUBLISHER.repository}/releases/download/{request.tag}/{name}"
    run(["curl", "-q", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
         "--proto-redir", "=https", "--connect-timeout", "15", "--max-time", "110",
         "--max-redirs", "5", "--max-filesize", str(limit), url, "--output", str(destination)])
    bounded_read(destination, limit)


def install(request):
    if os.getuid() == 0 or os.geteuid() != os.getuid() or platform.system() not in ("Darwin", "Linux"):
        raise ValueError("Install requires a non-root macOS or Linux user")
    for tool in ("bash", "gh", "curl", "jq"):
        if shutil.which(tool) is None:
            raise ValueError(f"Required trusted tool missing: {tool}")
    version = run(["curl", "-q", "--version"]).decode().split()[1]
    if tuple(int(part) for part in version.split(".")[:2]) < (8, 4):
        raise ValueError("curl 8.4.0 or later is required")
    gh_version = run(["gh", "--version"]).decode().split()[2]
    if tuple(int(part) for part in gh_version.split(".")[:2]) < (2, 103):
        raise ValueError("gh 2.103.0 or later is required")
    private = Path(run([sys.executable, "-I", "-c", STAGING_CODE]).decode().strip())
    try:
        archive = private / "package.tar.gz"
        download(request.release, f"tailmux-{request.release.tag}.tar.gz", archive, MAX_COMPRESSED)
        verified = authenticate(archive, request.release, bundle=request.bundle)
        stage = unpack(verified, Path(private))
        environment = {key: os.environ[key] for key in ("PATH", "HOME", "ZDOTDIR") if key in os.environ}
        environment.update({"LC_ALL": "C", "TMPDIR": str(private)})
        command = ["bash", str(stage / "setup.sh"), "install"]
        if request.prefix is not None:
            command += ["--prefix", str(request.prefix)]
        subprocess.run(command, check=True, env=environment, timeout=120)
    finally:
        shutil.rmtree(private)


def build_installer(root, request, destination):
    for reference in ("HEAD", f"refs/tags/{request.tag}^{{commit}}"):
        if git(root, "rev-parse", reference).decode().strip() != request.source_sha:
            raise ValueError("Installer source and tag must match expected source")
    path = "scripts/release/package.py"
    entry = git(root, "ls-tree", request.source_sha, "--", path).decode().split()
    if len(entry) != 4 or entry[:2] != ["100644", "blob"] or entry[3] != path:
        raise ValueError("Installer must be a regular committed module")
    if not 0 < int(git(root, "cat-file", "-s", entry[2])) <= MAX_INSTALLER:
        raise ValueError("Committed installer exceeds limit")
    with destination.open("xb") as stream:
        stream.write(git(root, "cat-file", "blob", entry[2]))


STAGING_CODE = r'''
import os, pathlib, platform, stat, subprocess, tempfile
uid = os.getuid()
if uid == 0 or os.geteuid() != uid:
    raise SystemExit("Run the installer as a non-root user.")
value = os.environ.get("TMPDIR") or tempfile.gettempdir()
base = pathlib.Path(value)
if not base.is_absolute() or "\n" in value or any(p in (".", "..") for p in value.split("/")):
    raise SystemExit("TMPDIR must be absolute without dot components or newlines.")
if platform.system() == "Darwin":
    if value == "/tmp" or value.startswith("/tmp/") or value == "/var" or value.startswith("/var/"):
        base = pathlib.Path("/private" + value)
for path in (*reversed(base.parents), base):
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in (0, uid):
        raise SystemExit("Unsafe TMPDIR directory or ancestry.")
    if metadata.st_mode & 0o022 and not (metadata.st_uid == 0 and metadata.st_mode & stat.S_ISVTX):
        raise SystemExit("Shared writable TMPDIR ancestry requires a root-owned sticky directory.")
    command = ["ls", "-lde" if platform.system() == "Darwin" else "-ld", str(path)]
    listing = subprocess.run(command, check=True, capture_output=True, text=True,
                             env={"PATH": os.environ["PATH"], "LC_ALL": "C"}, timeout=10).stdout.rstrip("\n")
    lines = listing.splitlines()
    if ("+" in lines[0].split()[0] or len(lines) > 1) and not (
            platform.system() == "Darwin" and lines[1:] == [" 0: group:everyone deny delete"]):
        raise SystemExit("Unknown TMPDIR ancestor ACLs are refused.")
private = pathlib.Path(tempfile.mkdtemp(prefix="tailmux-install-", dir=base))
try:
    private.chmod(0o700)
    command[-1] = str(private)
    listing = subprocess.run(command, check=True, capture_output=True, text=True,
                             env={"PATH": os.environ["PATH"], "LC_ALL": "C"}, timeout=10).stdout.rstrip("\n")
    if "+" in listing.split()[0] or "\n" in listing:
        raise SystemExit("Inherited staging ACLs are refused.")
except BaseException:
    private.rmdir()
    raise
print(private)
'''

BOOTSTRAP = r'''env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" ZDOTDIR="${ZDOTDIR:-$HOME}" bash <<'TAILMUX_INSTALL'
set -euo pipefail
umask 077
tag=@TAG@
source_sha=@SOURCE@
fail() { printf 'Tailmux install rejected: %s\n' "$1" >&2; exit 1; }
case "$(uname -s)" in Darwin|Linux) ;; *) fail 'Only macOS and Linux are supported.' ;; esac
for tool in python3 gh jq curl; do command -v "$tool" >/dev/null || fail "Required trusted tool missing: $tool"; done
python3 -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or later is required.")'
gh_version=$(gh --version)
gh_version=${gh_version#gh version }
gh_version=${gh_version%% *}
gh_major=${gh_version%%.*}
gh_minor=${gh_version#*.}; gh_minor=${gh_minor%%.*}
[[ $gh_major =~ ^[0-9]+$ && $gh_minor =~ ^[0-9]+$ ]] || fail 'Cannot read trusted gh version.'
(( gh_major > 2 || (gh_major == 2 && gh_minor >= 103) )) || fail 'gh 2.103.0 or later is required.'
curl_version=$(curl -q --version)
curl_version=${curl_version#curl }; curl_version=${curl_version%% *}
curl_major=${curl_version%%.*}
curl_minor=${curl_version#*.}; curl_minor=${curl_minor%%.*}
[[ $curl_major =~ ^[0-9]+$ && $curl_minor =~ ^[0-9]+$ ]] || fail 'Cannot read trusted curl version.'
(( curl_major > 8 || (curl_major == 8 && curl_minor >= 4) )) || fail 'curl 8.4.0 or later is required.'
private=$(python3 -I - <<'TAILMUX_STAGE'
@STAGING@
TAILMUX_STAGE
)
trap 'rm -rf -- "$private"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
asset="tailmux-${tag}-installer.py"
bundle="tailmux-${tag}.sigstore.json"
base="https://github.com/ddv1982/tailmux/releases/download/${tag}"
fetch() {
  curl -q --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 110 --max-redirs 5 --max-filesize "$2" \
    "$base/$1" --output "$private/$1"
  size=$(wc -c < "$private/$1")
  (( size > 0 && size <= $2 )) || fail 'Empty or oversized release asset.'
}
fetch "$asset" 1048576
fetch "$bundle" 2097152
GH_HOST=github.com GH_PROMPT_DISABLED=1 gh attestation verify "$private/$asset" \
  --hostname github.com --bundle "$private/$bundle" --repo ddv1982/tailmux \
  --signer-workflow ddv1982/tailmux/.github/workflows/release.yml \
  --signer-digest "$source_sha" --source-ref "refs/tags/$tag" \
  --source-digest "$source_sha" --deny-self-hosted-runners --format json \
  | head -c 1048577 > "$private/verified.json"
(( $(wc -c < "$private/verified.json") <= 1048576 )) || fail 'Oversized verifier result.'
jq -e -s 'length == 1 and (.[0] | type == "array" and length > 0 and all(.[];
  .verificationResult.signature.certificate as $c |
  $c.sourceRepositoryIdentifier == "1144643418" and
  $c.sourceRepositoryOwnerIdentifier == "240215896"))' "$private/verified.json" >/dev/null \
  || fail 'Verified publisher IDs do not match.'
python3 -I "$private/$asset" install --tag "$tag" --source-sha "$source_sha" --bundle "$private/$bundle"
TAILMUX_INSTALL
'''


def bootstrap_command(request):
    return (BOOTSTRAP.replace("@TAG@", request.tag).replace("@SOURCE@", request.source_sha)
            .replace("@STAGING@", STAGING_CODE.strip()))


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
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or later is required")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "build-installer", "bootstrap-command", "verify", "install"):
        command = commands.add_parser(name)
        command.add_argument("--tag", required=True)
        command.add_argument("--source-sha", required=True)
        if name in ("build", "build-installer"):
            command.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent.parent)
            command.add_argument("--output", type=Path, required=True)
        if name == "verify":
            command.add_argument("archive", type=Path)
            command.add_argument("--output-parent", type=Path, required=True)
        if name in ("verify", "install"):
            command.add_argument("--bundle", type=Path)
        if name == "install":
            command.add_argument("--prefix", type=Path)

    args = parser.parse_args()
    try:
        request = ReleaseRequest(args.tag, args.source_sha)
        if args.command == "build":
            build(args.root, request, args.output)
            print(args.output)
        elif args.command == "build-installer":
            build_installer(args.root, request, args.output)
            print(args.output)
        elif args.command == "bootstrap-command":
            print(bootstrap_command(request), end="")
        elif args.command == "install":
            install(InstallRequest(request, args.prefix, args.bundle))
        else:
            print(unpack(authenticate(args.archive, request, bundle=args.bundle), args.output_parent))
    except (ValueError, TypeError, IndexError, OSError, EOFError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Release rejected: {error}\n")


if __name__ == "__main__":
    main()
