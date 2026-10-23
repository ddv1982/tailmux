# Using Tailmux

Install the client, prepare the destination once, then connect by device name.

## Install, update, and uninstall

The verified shell entrypoint in the README accepts `install`, `update`, or `uninstall`.
It authenticates the pinned release installer and package before running the packaged setup code.
No GitHub login or repository checkout is required. All three actions need network access and the installer prerequisites listed in the README.
This entrypoint currently targets v0.2.2. Obtain an updated command from the trusted README when a newer release is available.

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
Setup adds no PATH entry or shell code. The absolute executable path works without changing your shell.
To use bare `tailmux` in your current Bash or Zsh session, run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

To keep this PATH entry across terminals, save that line in the startup file your shell loads.
An existing alias or loaded function can still shadow the executable. Use the absolute path while you inspect your shell configuration.
Install and update dependencies through their package owners.

## Prepare the destination

Tailmux uses `tailscale ssh` for the remote terminal. Tailscale carries the connection over its private network and manages authentication and access.
The local OpenSSH client still runs the SSH protocol. You do not need a separate OpenSSH server for Tailscale SSH.

First, install and sign in to Tailscale on both devices. On the destination:

1. Install tmux through your package manager. Run `tmux -V` as the account you plan to use to confirm that tmux is on its PATH.
2. Enable Tailscale SSH from the device's local terminal. This can interrupt existing SSH sessions over Tailscale.

   ```bash
   sudo tailscale set --ssh
   ```

3. Have your tailnet administrator allow network access to destination port 22 and Tailscale SSH access to the intended account.
   The account must already exist on the destination. See [Tailscale SSH setup](https://tailscale.com/docs/features/tailscale-ssh#configure-tailscale-ssh).

Tailscale SSH server support is available on Linux and the macOS open-source CLI variant.
Check [platform and macOS build requirements](compatibility.md) before using a Mac as the client or destination.
Tailmux installation does not configure destination access or install tmux.

## Connect and resume a session

Replace `device-name` with the destination's Tailscale name:

```bash
"$HOME/.local/bin/tailmux" device-name
```

Tailmux attaches to an existing tmux session or creates one.
If you need a different destination account, use `user@device-name`.
With the default tmux key bindings, press Ctrl-b, release both keys, then press d.
This returns you to your local terminal and leaves the session running.
Run the same connection command to resume later.

For a check without opening SSH, run:

```bash
"$HOME/.local/bin/tailmux" doctor device-name
```

This checks device selection and advertised host keys. It does not test SSH authorization or remote tmux.
See [troubleshooting](troubleshooting.md) if the check fails.

## Device selection

Pass one device name, optionally prefixed with `user@`.
Names ignore ASCII case and one trailing dot. Short names use the current tailnet's MagicDNS suffix.
A shared device outside that suffix needs its full canonical name or a configured alias.
Reported hostnames alone do not establish identity.

Exact advertised Tailscale addresses are also supported. Address ranges alone do not establish membership.
IPv6 accepts the advertised hexadecimal spelling, ignoring case; alternate compression, brackets, zone identifiers, and embedded IPv4 are unsupported.
Unknown or ambiguous selections fail before connecting. Tailmux never falls back to ordinary SSH or system DNS.
Extra options, remote commands, session names, and SSH flags are rejected.

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

## Migrate an older installation

Setup removes only exact fingerprinted legacy core or Taildrive managed blocks from standard shell RC files.
Unknown bodies or malformed markers cause refusal. Unmanaged content remains unchanged.
A symlinked RC containing a managed block needs manual migration through its dotfiles owner.
On macOS, recognized removal preserves surrounding bytes and supported metadata and saves a protected backup beside the RC.
On Linux, migration checks inode flags and extended attributes and preserves them in the replacement and backup.
It requires GNU cp, lsattr, and Python 3. Unsupported inode flags or unverifiable metadata need manual migration.
Use v0.2.1 or later for automatic Linux migration. The earlier v0.2.0 package requires manual legacy-block removal.
The installer never executes RC contents. Existing shells may retain previously loaded functions.

Taildrive helpers were removed; see [legacy Taildrive migration](taildrive.md).
See [compatibility](compatibility.md) for the remaining live SSH, host-key, policy, and terminal acceptance gaps.

## Optional Sentry error reporting

Available in v0.2.2 and later.
Reporting is off unless you set `TAILMUX_SENTRY_DSN` to your Sentry project's HTTPS DSN.
It needs curl; a missing curl or failed upload leaves the original error and exit status intact.

```bash
export TAILMUX_SENTRY_DSN='https://YOUR_PUBLIC_KEY@YOUR_INGEST_HOST/YOUR_PROJECT_ID'
export TAILMUX_SENTRY_ENVIRONMENT=production
```

Use a public 32-character hexadecimal key, DNS ingest host, and numeric project ID, as in a Sentry Cloud DSN.
For local testing, set `TAILMUX_SENTRY_ENVIRONMENT=development`.
Reports use `tailmux@<version>` as the release; source builds can set `TAILMUX_SENTRY_RELEASE=tailmux@<commit>`.
Environment names accept letters, numbers, underscores, and hyphens (up to 64 characters).
Release names also accept `@`, `.`, and `+` (up to 128 characters).
An unsupported DSN, environment, or release disables reporting for that invocation.

Only dependency, daemon, status-validation, and local I/O failures are reported.
Events contain a fixed error category, a relative source location, release, and environment.
They exclude selectors, device names, addresses, usernames, aliases, status snapshots, diagnostic text, and shell environment values.
Sentry still receives the network request's source IP; configure server-side scrubbing if you need that removed.
User-input errors, normal connection exits, and failures inside Tailscale SSH or remote tmux are not captured.
Each report can delay failure exit by up to three seconds. There is no retry queue or performance tracing.
Disable reporting with `unset TAILMUX_SENTRY_DSN`.
