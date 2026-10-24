#!/usr/bin/env bash
env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" ZDOTDIR="${ZDOTDIR:-$HOME}" bash -s -- "$@" <<'TAILMUX_INSTALL'
set -euo pipefail
umask 077
tag=v0.3.0
source_sha=877f8ffedacb68c8f78d0ce38ed506a4456d96ab
action=${1:-install}
if [[ $# -gt 0 ]]; then shift; fi
fail() { printf 'Tailmux setup rejected: %s\n' "$1" >&2; exit 1; }
case "$action" in
  install|update|uninstall|recover|configure) ;;
  --help|-h)
    [[ $# == 0 ]] || fail 'Help takes no options.'
    printf '%s\n' \
      'Usage: bash install.sh [install|update|uninstall] [--prefix ABS]' \
      '       bash install.sh recover [--prefix ABS] --dry-run' \
      '       bash install.sh recover [--prefix ABS] --expect-current-sha256 LOWER64HEX' \
      '       bash install.sh recover [--prefix ABS] --resume|--rollback|--unlock-abandoned --transaction ID --expect-current-sha256 LOWER64HEX' \
      '       bash install.sh configure --socket ABS_SOCKET' \
      '--unlock-abandoned asserts that no lifecycle writer remains active.'
    exit 0 ;;
  *) fail 'Expected install, update, uninstall, recover, or configure.' ;;
esac
prefix="$HOME/.local/bin"
prefix_seen=false
recovery=(apply '' '')
recovery_action_seen=false
socket=''
socket_seen=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      [[ "$action" != configure && $# -ge 2 && "$prefix_seen" == false ]] || fail 'Expected one lifecycle prefix.'
      prefix=$2
      prefix_seen=true
      shift 2 ;;
    --dry-run|--resume|--rollback|--unlock-abandoned)
      [[ "$action" == recover && "$recovery_action_seen" == false ]] || fail 'Expected one recovery operation.'
      recovery[0]=${1#--}
      recovery_action_seen=true
      shift ;;
    --expect-current-sha256|--transaction)
      [[ "$action" == recover && $# -ge 2 ]] || fail 'Expected a recovery value.'
      if [[ "$1" == --transaction ]]; then field=2; else field=1; fi
      [[ -z "${recovery[$field]}" && -n "$2" ]] || fail 'Duplicate or empty recovery value.'
      recovery[field]=$2
      shift 2 ;;
    --socket)
      [[ "$action" == configure && $# -ge 2 && "$socket_seen" == false ]] || fail 'Expected one configuration socket.'
      socket=$2
      socket_seen=true
      shift 2 ;;
    *) fail 'Unknown or incompatible option.' ;;
  esac
done
validate_request() {
  local LC_ALL=C id
  if [[ "$action" == configure ]]; then
    [[ "$socket_seen" == true && "$socket" == /* && ! "$socket" =~ [[:cntrl:]] && ${#socket} -le 8166 ]] || fail 'Expected an absolute socket without control bytes within the config limit.'
  else
    [[ "$prefix" == /* && ! "$prefix" =~ [[:cntrl:]] ]] || fail 'Expected an absolute prefix without control bytes.'
    case "/$prefix/" in */./*|*/../*) fail 'Prefix dot components are refused.' ;; esac
  fi
  if [[ "$action" == recover ]]; then
    case "${recovery[0]}" in
      dry-run) [[ -z "${recovery[1]}${recovery[2]}" ]] || fail 'Preview takes no approval or transaction.' ;;
      apply) [[ -z "${recovery[2]}" ]] || fail 'Transaction requires a maintenance operation.' ;;
      *)
        id=${recovery[2]}
        [[ ${#id} -ge 1 && ${#id} -le 96 && "$id" != . && "$id" != .. && "$id" != *[!a-zA-Z0-9._-]* ]] || fail 'Invalid transaction ID.' ;;
    esac
    if [[ "${recovery[0]}" != dry-run ]]; then
      [[ "${recovery[1]}" =~ ^[a-f0-9]{64}$ ]] || fail 'Expected a lowercase current SHA256.'
    fi
  fi
}
validate_request
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
request=("$action" --prefix "$prefix")
case "$action" in
  update)
    request=(install --prefix "$prefix")
    if [[ -e "$prefix/tailmux" || -L "$prefix/tailmux" ]]; then
      [[ -f "$prefix/tailmux" && ! -L "$prefix/tailmux" ]] || fail 'Existing client must be a regular, non-symlinked file.'
      request+=(--replace-owned)
    fi ;;
  configure) request=(configure --socket "$socket") ;;
  recover)
    if [[ "${recovery[0]}" == dry-run ]]; then
      request+=(--dry-run)
    else
      request+=(--expect-current-sha256 "${recovery[1]}")
      if [[ "${recovery[0]}" != apply ]]; then
        request+=("--${recovery[0]}" --transaction "${recovery[2]}")
      fi
    fi ;;
esac
bash "$verified/setup.sh" "${request[@]}"
TAILMUX_INSTALL
