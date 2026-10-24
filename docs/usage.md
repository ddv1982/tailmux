# Using Tailmux

Install the client, prepare the destination once, then connect by device name.

## Install, update, and uninstall

The verified shell entrypoint in the README accepts `install`, `update`, or `uninstall`.
It authenticates the pinned release installer and package before running the packaged setup code.
No GitHub login or repository checkout is required. All three actions need network access and the installer prerequisites listed in the README.
This entrypoint currently targets v0.2.3. Obtain an updated command from the trusted README when a newer release is available.

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

1. Install tmux through your package manager. It must be on the PATH used by remote SSH commands, which can differ from your interactive shell.
2. Enable Tailscale SSH from the device's local terminal. This can interrupt existing SSH sessions over Tailscale.

   ```bash
   sudo tailscale set --ssh
   ```

3. Have your tailnet administrator allow network access to destination port 22 and Tailscale SSH access to the intended account.
   The account must already exist on the destination. See [Tailscale SSH setup](https://tailscale.com/docs/features/tailscale-ssh#configure-tailscale-ssh).

Tailscale SSH server support is available on Linux and the macOS open-source CLI variant.
Check [platform and macOS build requirements](compatibility.md) before using a Mac as the client or destination.
Tailmux installation does not configure destination access or install tmux.
If tmux works locally but Tailmux cannot find it, [check the remote command PATH](troubleshooting.md#resolve-tmux-not-found-on-remote).

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

## Select a Tailscale daemon

Environment selection is available in v0.2.3.
The saved-setting commands below require the client from this checkout, installed through local `setup.sh`.
The published v0.2.3 installer does not include those commands yet.
Tailmux uses the `tailscale` executable on your PATH.
On a Mac with both the Tailscale app and a separate CLI service, these can represent different devices.
Use the socket path supplied by your Tailscale installation. No socket path is a universal default.

To save your daemon selection across terminals and client updates, run:

```bash
"$HOME/.local/bin/tailmux" --config set socket /var/run/tailscaled.socket
"$HOME/.local/bin/tailmux" --config show
"$HOME/.local/bin/tailmux" doctor
```

`show` prints the saved socket, effective socket, selection source, and PATH-selected CLI without invoking Tailscale.
Doctor shows the selection source in its existing daemon row.
The same socket applies to all version probes, peer discovery, and SSH.
An unavailable selected daemon causes failure. Tailmux never retries another endpoint.
Quote paths that contain spaces or shell punctuation. Paths remain literal data.

An explicitly set `TAILMUX_TAILSCALE_SOCKET` overrides the saved socket.
An empty, relative, or control-containing environment value fails before daemon access.
For connections and doctor, a valid environment value bypasses the saved file, even when that file is malformed or unsafe.
`--config show` also inspects saved state and reports file errors without invoking a daemon.
For a temporary override, run:

```bash
TAILMUX_TAILSCALE_SOCKET=/var/run/another.socket "$HOME/.local/bin/tailmux" doctor
```

To remove the saved socket, run:

```bash
"$HOME/.local/bin/tailmux" --config reset socket
unset TAILMUX_TAILSCALE_SOCKET
```

Reset leaves any environment override in effect and explains that in its output.
With neither setting present, Tailmux uses the Tailscale CLI's native default endpoint.
Set and reset never invoke Tailscale or perform network work, including optional error reporting on failure.
All config commands dispatch before connection settings are validated, so an invalid override cannot block repair.
Help and version also ignore configuration and dependencies. `tailmux config` remains a peer selector.

Tailmux stores exactly two LF-terminated records in `$HOME/.config/tailmux/config`:

```text
tailmux-config-v1
socket=/var/run/tailscaled.socket
```

The maximum file size is 8 KiB. The socket must be absolute and contain no ASCII control bytes.
Extra records, unknown versions, NULs, missing final LF, and empty or relative values fail before daemon access.
There is no shell evaluation, tilde expansion, or path splitting.
Config and hosts retain their fixed HOME paths. `XDG_CONFIG_HOME` does not relocate them.

Reads and writes refuse symlinked config files and ancestors, including user-owned dotfiles links.
Manage those paths through your dotfiles owner before using saved settings.
The config must be current-user owned, mode `0600`, regular, and have one hard link.
Its HOME-side directories must be current-user owned and not group or other writable.
Unknown or mutating ACLs cause refusal. The OS-provided macOS directory ACL that denies deletion is accepted.
New directories are private. Existing safe directory permissions remain unchanged.

If current-version data is malformed, inspect it with `--config show`, then use `--config reset socket`.
Reset creates a mode `0600` `config.backup.*` beside the config and verifies identical content before clearing the setting.
The backup preserves content only. Keep it for inspection, then save the correct socket again.
Set refuses malformed data until reset succeeds.
Unknown-version, linked, unsafe, unreadable, and oversized files remain untouched. The error identifies their path.

One `.config-lock` directory serializes config writers.
Caught failures and SIGTERM clean up the current writer's lock and unpublished stage when possible.
SIGKILL can leave a lock. Tailmux never removes a lock by age or PID.
An existing lock requires owner inspection after ensuring that no config writer remains active.
Atomic publication keeps the previous or complete replacement config visible. A nonzero exit after publication can leave the new setting applied.
No power-loss durability guarantee follows from shell traps.
Installation, update, and uninstall preserve saved config and hosts.
Tailmux never edits shell files for saved settings and does not start, stop, or configure services.

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
