# tailmux

Access tmux sessions on your Tailscale devices from anywhere.

## Quick Start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ddv1982/tailmux/main/setup.sh)
```

This will prompt you to:
- Install Tailscale
- Install tmux
- Add the `tailmux` command to your shell

Before connecting, make sure SSH is enabled on the destination:
- macOS: System Settings → General → Sharing → Remote Login
- Linux: `sudo systemctl enable --now ssh` (or `sshd`)

## Usage

```bash
tailmux <hostname>
```

Connects to the host via SSH over Tailscale and attaches to an existing tmux session (or creates a new one).

- `hostname` - Tailscale device name or IP

**Tip:** Use `tailscale status` to list all devices with their hostnames and IPs - handy for troubleshooting connection issues.

**Examples:**

```bash
tailmux macbook-pro       # connect by device name
tailmux 100.101.102.103   # connect by your Tailscale IP (from `tailscale status`)
```

## Uninstall

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ddv1982/tailmux/main/setup.sh) uninstall
```

## Supported Platforms

| OS | Package Manager | SSH Server Support |
|----|-----------------|-------------------|
| macOS | Homebrew | Yes (Remote Login) |
| Debian/Ubuntu | apt | Yes |
| Fedora | dnf | Yes |
| RHEL/CentOS | yum | Yes |
| Arch Linux | pacman | Yes |
| Windows | - | Use WSL |

## Notes

- Your tailnet ACLs must allow SSH (port 22) to the destination
- You can set simpler machine names in the [Tailscale admin console](https://login.tailscale.com/admin/machines) by clicking on a device and editing its name
