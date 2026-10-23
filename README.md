# tailmux

Resume tmux sessions on your Tailscale devices with one command.
Tailmux connects through Tailscale SSH, attaches to an existing session, or creates one.

## Install, update, or uninstall

Supports macOS and Linux. Install trusted Python 3.11+, gh 2.103.0+, jq, and curl 8.4.0+ first.
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

The client is installed at `~/.local/bin/tailmux`. Setup preserves your dependencies and unmanaged shell configuration.
See [installation options and migration](docs/usage.md#install-update-and-uninstall) for custom paths, local setup, and backups.

## Connect

Use your device's Tailscale name:

```bash
"$HOME/.local/bin/tailmux" device-name
```

The destination needs tmux, Tailscale SSH enabled, and policy permission.
Run `tailmux doctor` to check local dependencies.

## Documentation

- [Usage and aliases](docs/usage.md)
- [Optional Sentry error reporting](docs/usage.md#optional-sentry-error-reporting)
- [Troubleshooting](docs/troubleshooting.md)
- [Compatibility and remaining live-test gaps](docs/compatibility.md)
- [Installer verification and releases](docs/releases.md)
- [Development](docs/development.md)

[MIT License](LICENSE).
