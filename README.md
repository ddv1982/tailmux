# tailmux

Tailmux selects a known Tailscale peer and resumes a tmux session through `tailscale ssh`.
It attaches to any existing session, or creates one when attachment fails.

## Install the local client

Use a reviewed local checkout:

```bash
bash setup.sh install
"$HOME/.local/bin/tailmux" --version
```

The client version is `0.2.0-dev`.
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
Authenticated SSH, key mismatch, policy denial, interactive terminals, and Linux platform behavior still need the parent plan's isolated live evidence.
Local test success is not a release-ready verdict.
Taildrive helpers have been removed. See [legacy Taildrive migration](docs/taildrive.md).

## Development

```bash
bash scripts/tests/run.sh lint
bash scripts/tests/run.sh quick
bash scripts/tests/run.sh full
bash scripts/tests/smoke.sh
```

Tests require Python 3 standard library, jq, and ShellCheck.
Runtime requires no Python.
Fixtures contain sanitized synthetic public records and faithful legacy RC bytes.
Tests invoke the actual executable and setup CLI in disposable homes with fake transport and administration commands.
Each subprocess receives an explicit environment with only required paths, locale, shell, and test controls.

Released under the [MIT License](LICENSE).
