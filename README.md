# tailmux

Connect to an SSH destination and resume or create a tmux session.

```bash
tailmux macbook-pro
tailmux 100.101.102.103
```

## Prerequisites

Use Bash on macOS or Linux to run setup. The legacy function runs in Bash or Zsh.
Install and maintain Tailscale through its existing package or application owner.
The client needs OpenSSH. The destination account needs tmux in its noninteractive shell PATH and an SSH service that permits access.
Setup checks Tailscale availability without contacting its daemon. It can install the function before Tailscale is available.

Client setup does not install, update, or remove packages. It does not change services, operator privileges, authentication, Tailscale SSH settings, applications, policy, or Tailscale state.
Destination server configuration belongs to its operator. Client installation does not require enabling an inbound SSH server on your own device.

## Install from a reviewed checkout

Inspect the local checkout, then run:

```bash
bash setup.sh install
```

Setup uses only that checkout's modules. Remote process-substitution installation is disabled until a reviewed release distribution path exists.
Open a fresh shell after setup.

This unit still installs the reviewed legacy core function into your shell RC file. The standalone executable and resolver migration are separate work.
For Zsh, setup uses `${ZDOTDIR:-$HOME}/.zshrc`. For Bash, it chooses the first existing `.bashrc` or `.bash_profile`, then falls back to `.profile`.

Install and uninstall preflight those four standard RC paths. They refuse unmanaged `tailmux` functions or aliases, unknown or modified core blocks, malformed markers, symlinks, and symlinked ancestors.
They recognize only the examined 0.1.0 core template and its PR-01 security patch.
RC files must be current-user owned, have one hard link, and forbid group or other writes. The direct parent must be current-user owned and forbid group or other writes too.
Ancestors must belong to the current user or root. Writable ancestors require the sticky bit.
RC-file ACLs require manual handling. Directory ACLs are refused except the exact macOS default entry `0: group:everyone deny delete`.
That deny-only entry can appear on the direct parent or a higher ancestor and remains unchanged. Unknown entries and mutating grants are refused.

Setup preserves bytes outside recognized core spans, owner, group, and mode. On macOS it preserves and verifies file flags and xattrs with the system copy and xattr tools. On Linux it requires GNU `cp` with explicit xattr preservation.
A changed RC gets a protected `.tailmux-backup.*` directory beside it before same-directory replacement.
Keep those backups until you have checked the result. A retry leaves an already-current block unchanged.

## Setup commands

```bash
bash setup.sh install
bash setup.sh uninstall
bash setup.sh update
bash setup.sh --help
bash setup.sh --version
```

Help and version work offline without loading any modules.
`update` returns a deprecation error without loading modules or running package commands. Use each dependency's existing package owner.
No command prompts for machine administration.

## Usage

```bash
tailmux <host>
tailmux doctor <host>
tailmux --help
tailmux --version
```

The legacy resolver tries direct IPs, the alias file, Tailscale status JSON, Tailscale DNS, optional LAN lookup, and system DNS. It passes unresolved names to SSH.
It does not enforce tailnet membership. Check the reported destination before connecting.
`TAILMUX_LAN_FALLBACK=1` enables the optional `<host>.local` lookup.

Aliases are data in `~/.config/tailmux/hosts`, or the path in `TAILMUX_HOSTS_FILE`:

```text
home 100.64.0.10
mini mini.example-tailnet.ts.net
```

Tailmux invokes local OpenSSH. Tailscale SSH applies when the destination runs that server and tailnet policy permits access.
Other destinations need their own SSH service and access controls. Keep SSH host-key checking enabled.
The remote account owns executable discovery. Tailmux does not copy the local PATH or add package-manager directories on the destination.

## Uninstall core functions

Run from the same reviewed local checkout:

```bash
bash setup.sh uninstall
```

Uninstall removes only recognized core blocks from the standard RC paths. It leaves packages, Tailscale identity, networking settings, mounts, shares, and legacy Taildrive blocks intact.
Open a fresh shell to discard loaded functions.
Arbitrary sourced dotfiles and other custom RC locations require manual inspection.
Inspection detects literal declarations. It cannot discover aliases or functions created dynamically or through other sourced files.
See [troubleshooting](docs/troubleshooting.md) for refusal and recovery guidance.

## Legacy Taildrive

Core setup no longer installs or manages Taildrive helpers or mount dependencies.
Existing helpers remain legacy code pending retirement during the executable migration.
See [Taildrive legacy support and removal](docs/taildrive.md) before using or removing an existing installation.

## Development

`setup.sh` loads local core lifecycle modules from `scripts/lib` after early CLI dispatch.
Runtime templates remain separate from package and server administration.
Tests use disposable homes and fake network, SSH, mount, package, and privilege commands.

```bash
bash scripts/tests/run.sh lint
bash scripts/tests/run.sh quick
bash scripts/tests/run.sh full
bash scripts/tests/smoke.sh
```

The full suite retains resolver, legacy Taildrive runtime, and PR-01 security regressions alongside the new installer lifecycle tests.
CI workflow hardening remains separate work.

## License

Released under the [MIT License](LICENSE).
