# Troubleshooting

## tailmux Connection Issues

- **Host not found / passthrough mode**: Run `tailmux doctor <hostname>` and `tailscale dns status --all` to check resolution.
- **Short hostnames fail**: On macOS with the open-source CLI, MagicDNS short names may not resolve. Use the tailnet FQDN or add a stable alias in `~/.config/tailmux/hosts`.
- **LAN fallback**: Set `TAILMUX_LAN_FALLBACK=1` to try `<host>.local` before giving up.
- **Connection refused on macOS**: Enable Remote Login in System Settings > General > Sharing.
- **Connection refused on Linux**: Run `sudo tailscale up --ssh` to enable Tailscale SSH.

## Tailscale on macOS

- **"tailscale: command not found"**: Ensure Homebrew's bin is in your PATH (`brew shellenv`), then run `brew link tailscale` to recreate CLI symlinks if needed.
- **"Is Tailscale running?"**: Start the daemon with `sudo brew services start tailscale` (sudo required for root privileges).
- **"failed to connect to local Tailscale service"**: Restart daemon with `sudo brew services restart tailscale`. If it still fails, remove stale artifacts and retry:
  - `rm -f /opt/homebrew/var/log/tailscaled.log`
  - `rm -f ~/Library/LaunchAgents/homebrew.mxcl.tailscale.plist`
  - `sudo rm -f /Library/LaunchDaemons/homebrew.mxcl.tailscale.plist`
  - `sudo brew services start tailscale`
- **Authentication**: Run `tailscale up` to authenticate (opens browser). If you hit a permissions error, retry with `sudo tailscale up`.
- **Switching from GUI app**: Setup can auto-remove Homebrew cask installs during migration. Standalone/App Store installs must be removed from Applications before setup will install the Homebrew formula.
- See: [Taildrive docs](https://tailscale.com/kb/1369/taildrive) and [macOS variants](https://tailscale.com/kb/1065/macos-variants)

## Linux Mounts

- If `tailmount` fails with `mount.davfs` missing, install `davfs2`:
  - Debian/Ubuntu: `sudo apt-get update -y && sudo apt-get install -y davfs2`
  - Fedora: `sudo dnf install -y davfs2`
  - RHEL/CentOS: `sudo yum install -y davfs2`
  - Arch: `sudo pacman -S --noconfirm davfs2`
- If mount/unmount requires elevated privileges, `tailmount`/`tailumount` will retry with `sudo`.
