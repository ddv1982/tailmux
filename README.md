# tailmux

Resume tmux sessions on your Tailscale devices with one command.
Tailmux connects through Tailscale SSH, attaches to an existing session, or creates one.

## Before you start

- On your Mac or Linux client, use Bash 3.2+, jq, OpenSSH, and a running Tailscale client that supports `tailscale ssh`.
- On the destination, install tmux and [enable Tailscale SSH and access](docs/usage.md#prepare-the-destination).

Tailscale SSH opens an SSH terminal over your private Tailscale network. Tailscale manages identity and access.
See [macOS build requirements](docs/compatibility.md) if you use the App Store or TestFlight app.

## Install, update, or uninstall

The installer needs trusted Python 3.11+, gh 2.103.0+, jq, and curl 8.4.0+.
Run this as your normal user to install [v0.2.2](https://github.com/ddv1982/tailmux/releases/tag/v0.2.2):

```bash
curl -qfsSL --proto '=https' --proto-redir '=https' --connect-timeout 15 \
  --max-time 110 --max-redirs 5 --max-filesize 65536 \
  https://raw.githubusercontent.com/ddv1982/tailmux/c6ee889418b4cbb8badabd3e5d145463c9f01d09/install.sh |
python3 -I -c 'import hashlib, os, subprocess, sys
script = sys.stdin.buffer.read(65537)
if hashlib.sha256(script).hexdigest() != "220b371f1efa1f8f88ec5665f34530950cd8c9bde742b3af07629a26ff8e8d7a": sys.exit("Installer checksum mismatch.")
env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "ZDOTDIR") if k in os.environ}
sys.exit(subprocess.run(["bash", "-s", "--", *sys.argv[1:]], input=script, env=env).returncode)
' install
```

For updates or removal, replace `install` on the last line with `update` or `uninstall`.
All three actions use the same [shell script](install.sh) and verify the signed release package. No GitHub login is needed.
Updates currently target v0.2.2; use the updated README command when a newer release is published.

The client is installed at `~/.local/bin/tailmux`. Setup adds no PATH entry or shell code.
See [installation options and migration](docs/usage.md#install-update-and-uninstall) for custom paths, local setup, and backups.

## Connect

Check local dependencies, then connect using your destination's Tailscale name:

```bash
"$HOME/.local/bin/tailmux" doctor
"$HOME/.local/bin/tailmux" device-name
```

Use `user@device-name` if the destination account differs from your local username.
For connection errors, see [troubleshooting](docs/troubleshooting.md).

## Documentation

- [Usage and aliases](docs/usage.md)
- [Optional Sentry error reporting](docs/usage.md#optional-sentry-error-reporting)
- [Troubleshooting](docs/troubleshooting.md)
- [Compatibility and remaining live-test gaps](docs/compatibility.md)
- [Installer verification and releases](docs/releases.md)
- [Development](docs/development.md)

[MIT License](LICENSE).
