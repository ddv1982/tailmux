#!/usr/bin/env bash
env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" ZDOTDIR="${ZDOTDIR:-$HOME}" bash -s -- "$@" <<'TAILMUX_INSTALL'
set -euo pipefail
umask 077
tag=v0.2.0
source_sha=d3dbae670a1a9f2429a3db825e91628a7dbb74bc
action=${1:-install}
if [[ $# -gt 0 ]]; then shift; fi
fail() { printf 'Tailmux setup rejected: %s\n' "$1" >&2; exit 1; }
case "$action" in
  install|update|uninstall) ;;
  --help|-h) printf '%s\n' 'Usage: bash install.sh [install|update|uninstall] [--prefix /absolute/bin/directory]'; exit 0 ;;
  *) fail 'Expected install, update, or uninstall.' ;;
esac
prefix="$HOME/.local/bin"
if [[ $# -gt 0 ]]; then
  [[ $# == 2 && $1 == --prefix ]] || fail 'Expected --prefix /absolute/bin/directory.'
  prefix=$2
fi
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
archive="tailmux-${tag}.tar.gz"
fetch "$archive" 8388608
verified=$(python3 -I "$private/$asset" verify "$private/$archive" \
  --tag "$tag" --source-sha "$source_sha" --bundle "$private/$bundle" --output-parent "$private")
if [[ $action == update ]]; then
  if [[ -e "$prefix/tailmux" || -L "$prefix/tailmux" ]]; then
    [[ -f "$prefix/tailmux" && ! -L "$prefix/tailmux" ]] || fail 'Existing client must be a regular, non-symlinked file.'
  fi
  if [[ -e "$prefix/tailmux" || -L "$prefix/tailmux" || -e "$prefix/.tailmux-receipt" || -L "$prefix/.tailmux-receipt" ]] &&
     ! cmp -s "$prefix/tailmux" "$verified/bin/tailmux"; then
    bash "$verified/setup.sh" uninstall --prefix "$prefix"
  fi
  action=install
fi
bash "$verified/setup.sh" "$action" --prefix "$prefix"
TAILMUX_INSTALL
