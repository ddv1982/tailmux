# Using Tailmux

Tailmux connects to a known Tailscale device and runs `tmux attach || tmux new`.
The destination account needs tmux on its PATH, Tailscale SSH enabled, and policy permission.
Locally, use Bash 3.2 or later, jq, Tailscale, and OpenSSH.

## Device selection

Pass one device name, optionally prefixed with `user@`.
Names ignore ASCII case and one trailing dot. Short names use the current tailnet's MagicDNS suffix.
A shared device outside that suffix needs its full canonical name or a configured alias.
Reported hostnames alone do not establish identity.

Exact advertised Tailscale addresses are also supported. Address ranges alone do not establish membership.
IPv6 accepts the advertised hexadecimal spelling, ignoring case; alternate compression, brackets, zone identifiers, and embedded IPv4 are unsupported.
Unknown or ambiguous selections fail before connecting. Tailmux never falls back to ordinary SSH or system DNS.
Extra options, remote commands, session names, and SSH flags are rejected.

Run `tailmux doctor` for local dependency diagnostics, or `tailmux doctor device-name` to check selection without connecting.
Help and version work offline.

## Aliases

Create `~/.config/tailmux/hosts` with one alias and full canonical device name per line:

```text
desktop desktop.example.ts.net
server server.example.ts.net
```

Aliases are data, never shell code. Blank lines and full-line comments are accepted.
Duplicate aliases, short targets, alias chains, usernames, shell syntax, and extra fields are rejected.
An alias takes precedence over the same short device name.
Use `TAILMUX_HOSTS_FILE` for another file; an explicit missing file is an error.

## Install, update, and uninstall

The verified shell entrypoint in the README accepts `install`, `update`, or `uninstall`.
It authenticates the pinned release installer and package before running the packaged setup code.
No GitHub login or repository checkout is required. All three actions need network access and the installer prerequisites listed in the README.
This entrypoint currently targets v0.2.0. Obtain an updated command from the trusted README when a newer release is available.

`install` creates the executable and ownership receipt in `~/.local/bin`.
Repeating installation of the same version is supported. It refuses to replace a different version; use `update` for that.
`update` verifies the replacement first, backs up and removes a different receipt-owned client, then installs the pinned release.
Repeating `update` on the same version preserves the existing installation.
`uninstall` verifies ownership, backs up the executable and receipt, and removes those owned files.
Repeating uninstall is supported.

A failed update can leave a protected backup and an incomplete installation. Resolve the reported error and retry; see [lifecycle troubleshooting](troubleshooting.md#resolve-lifecycle-refusals).
Modified files, foreign files, ambiguous ownership, unsafe destinations, and unknown locks cause refusal.
Dependencies, networking identity, unmanaged shell configuration, aliases, and backups remain under their existing owners.

For a trusted local checkout, installation and removal also work offline:

```bash
bash setup.sh install
bash setup.sh uninstall
```

For a custom binary directory, append `--prefix /absolute/path/bin` to the downloaded entrypoint's action, or to local setup.
Setup adds no PATH entry or shell code. Use the printed executable path if an alias or function shadows `tailmux`.
Install and update dependencies through their package owners.

## Migrate an older installation

Setup removes only exact fingerprinted legacy core or Taildrive managed blocks from standard shell RC files.
Unknown bodies or malformed markers cause refusal. Unmanaged content remains unchanged.
A symlinked RC containing a managed block needs manual migration through its dotfiles owner.
On macOS, recognized removal preserves surrounding bytes and supported metadata and saves a protected backup beside the RC.
On Linux, legacy markers require manual removal before lifecycle operations.
The installer never executes RC contents. Existing shells may retain previously loaded functions.

Taildrive helpers were removed; see [legacy Taildrive migration](taildrive.md).
See [compatibility](compatibility.md) for the remaining live SSH, host-key, policy, and terminal acceptance gaps.
