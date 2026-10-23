# tailmux

Tailmux selects a known Tailscale peer and resumes a tmux session through `tailscale ssh`.
It attaches to any existing session, or creates one when attachment fails.

## Install the local client

Install [Tailmux 0.2.0](https://github.com/ddv1982/tailmux/releases/tag/v0.2.0) without checking out the repository.
First install trusted Python 3.11 or later, gh 2.103.0 or later, jq, and curl 8.4.0 or later through their package owners.
The block verifies the source-pinned installer before execution and the package before installation. GitHub login is not required.
Run it as your normal user:

```bash
env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" ZDOTDIR="${ZDOTDIR:-$HOME}" bash <<'TAILMUX_INSTALL'
set -euo pipefail
umask 077
tag=v0.2.0
source_sha=d3dbae670a1a9f2429a3db825e91628a7dbb74bc
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
python3 -I "$private/$asset" install --tag "$tag" --source-sha "$source_sha" --bundle "$private/$bundle"
TAILMUX_INSTALL
```

Then run `"$HOME/.local/bin/tailmux" --version`.
See [publisher verification](docs/releases.md) for the trust model and manual verification path.

To install from a reviewed local checkout instead:

```bash
bash setup.sh install
"$HOME/.local/bin/tailmux" --version
```

The client version is `0.2.0`.
Setup installs one executable and a small ownership receipt under `~/.local/bin`.
For another destination, pass an absolute binary directory:

```bash
bash setup.sh install --prefix "/absolute/path/bin"
bash setup.sh uninstall --prefix "/absolute/path/bin"
```

Setup adds no PATH entry or shell code.
Use the printed absolute executable path if your shell does not find it.
An existing alias, function, or loaded legacy function can shadow bare `tailmux`.
The installer preserves unmanaged shell code and does not claim to discover every declaration.

You need Bash 3.2 or later, jq, Tailscale, and OpenSSH locally.
The destination needs tmux, operator-configured Tailscale SSH, policy permission, and advertised SSH host keys.
Install and update dependencies through their existing package owners.
Setup never installs packages, changes apps or services, enables servers, assigns operators, logs out, or removes networking state.

## Connect to a known peer

```bash
"$HOME/.local/bin/tailmux" work
"$HOME/.local/bin/tailmux" alice@work.example.ts.net
"$HOME/.local/bin/tailmux" 100.64.0.20
"$HOME/.local/bin/tailmux" fd7a:115c:a1e0::2
"$HOME/.local/bin/tailmux" doctor work
"$HOME/.local/bin/tailmux" doctor
```

Connect accepts exactly one selector, optionally prefixed with `user@`.
Doctor without a selector reports active local paths, separate CLI and daemon versions, and a dated dependency-policy classification.
Vendor patch status remains unknown without build-specific evidence. See [the dependency policy](docs/dependencies.md).
Doctor with a selector resolves it without SSH.
Help and version work offline without dependencies.
Extra options, remote commands, session names, and SSH flags are rejected.

Selectors match a canonical peer DNS name or an exact advertised address in one status snapshot.
Canonical names ignore ASCII case and one trailing dot.
Short names match only within the current `CurrentTailnet.MagicDNSSuffix`.
A shared peer outside that suffix needs its full canonical name, address, or an explicit alias.
Reported `HostName` is never identity evidence.
IPv6 selectors use the advertised hexadecimal spelling, ignoring case.
Equivalent compression spellings, brackets, zone identifiers, and embedded IPv4 notation are unsupported.

An unknown or ambiguous selector fails before transport.
Address ranges alone never establish membership.
The client checks the selected canonical name and every selected-peer address against all visible peer records, including stale records and records without keys.
`Online:false` is advisory.
`Expired:true` prevents connection with `peer-key-expired`.
No error falls back to system DNS, mDNS, raw SSH, another user, or weaker host-key verification.

## Define declarative aliases

Create `~/.config/tailmux/hosts` as data:

```text
# Short label followed by a full canonical name or advertised address
home work.example.ts.net
shared shared.other.ts.net
build 100.64.0.20
```

Set `TAILMUX_HOSTS_FILE` to select another file.
A missing default file is optional.
A missing explicit override is an error.
Blank lines and full-line comments are accepted.
Every other line has exactly two fields.
Duplicate normalized labels, short targets, alias chains, extra fields, usernames, and shell syntax are rejected.
The client never sources or evaluates the file.
An alias takes precedence over the same short canonical label.

## Migrate and uninstall

Install and uninstall inspect standard Bash RC files and `${ZDOTDIR:-$HOME}/.zshrc` as data.
They remove only exact fingerprinted legacy core or Taildrive managed blocks.
Malformed markers or modified bodies cause refusal before lifecycle writes.
Unmanaged aliases, functions, and sourced code remain byte-for-byte unchanged.
A symlinked RC containing a managed block requires manual migration through your dotfiles owner.
An unrelated symlinked RC can remain untouched.
On macOS, recognized block removal preserves surrounding bytes, verifies flags and xattrs, and saves a protected backup beside the RC.
On Linux, any legacy managed markers cause refusal before lifecycle writes. Remove legacy blocks through your dotfiles owner and retry.
Linux fresh installation and uninstall remain available when no managed RC block needs changing.
The installer never executes RC contents.

```bash
bash setup.sh uninstall
```

Uninstall verifies the executable path and digest against its receipt, saves content-only backups of owned client files, then removes them.
These client backups do not promise metadata preservation.
Foreign files, modified files, hardlinks, and ambiguous links are refused.
Aliases, unrelated files, backups, dependency packages, and networking identity remain.
Repeat install and uninstall are supported.
For a different installed version, uninstall it through a reviewed checkout before installing this one.
`bash setup.sh update` is deprecated and performs no update.
Remote and process-substitution setup are disabled.

## Compatibility and verification

The status schema and wrapper argument order are grounded in Tailscale v1.104.2.
The serialized host-key field is `sshHostKeys`.
App Store and TestFlight builds do not provide this wrapper.
Their error remains explicit, with no app replacement or transport downgrade.
Remote PATH belongs to the destination account and is never copied from the caller.
The wrapper and deliberately configured local SSH configuration remain trusted.

Preflight and the wrapper use separate coordination snapshots.
Tailmux trusts current coordination identity and does not atomically pin a stable peer ID across an address reassignment.
See the [architecture reference](docs/architecture.md) and [troubleshooting guide](docs/troubleshooting.md).

This development client has local fixture and lifecycle tests.
Authenticated SSH, key mismatch, policy denial, interactive terminals, and Linux platform behavior still need the [isolated acceptance procedure](docs/acceptance.md).
See the [compatibility matrix](docs/compatibility.md) and [laptop smoke-test guide](docs/acceptance.md#inspect-the-reviewed-checkout-first).
Local test success is not a release-ready verdict.
Taildrive helpers have been removed. See [legacy Taildrive migration](docs/taildrive.md).

## Development

Install jq and ShellCheck through their package owners. Prepare a development-only virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
. .venv/bin/activate
bash scripts/tests/run.sh lint
bash scripts/tests/run.sh quick
bash scripts/tests/run.sh full
bash scripts/tests/smoke.sh
```

Tests require Python 3.11 through 3.14, the hashed development requirements, jq, and ShellCheck.
The full command runs every offline suite, including workflow and acceptance policy checks.
Actionlint is a separate workflow syntax check. No live host test runs through the offline suite.
Runtime requires no Python.
Fixtures contain sanitized synthetic public records and faithful legacy RC bytes.
Tests invoke the actual executable and setup CLI in disposable homes with fake transport and administration commands.
Each subprocess receives an explicit environment with only required paths, locale, shell, and test controls.

Released under the [MIT License](LICENSE).
