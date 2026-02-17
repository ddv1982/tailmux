# tailmux

Access tmux sessions on your Tailscale devices from anywhere.

```bash
tailmux macbook-pro       # connect by device name
tailmux 100.101.102.103   # connect by Tailscale IP
```

## Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Setup Commands](#setup-commands)
- [Usage](#usage)
- [File Sharing (Taildrive)](#file-sharing-taildrive)
- [Supported Platforms](#supported-platforms)
- [Uninstall](#uninstall)
- [Notes](#notes)
- [Development](#development)

## Prerequisites

- bash and curl
- A [Tailscale](https://tailscale.com) account
- Remote access enabled on the destination:
  - macOS: System Settings > General > Sharing > Remote Login
  - Linux: `sudo tailscale up --ssh` (no OpenSSH daemon required)

## Quick Start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ddv1982/tailmux/main/setup.sh)
```

This will:
- Install Tailscale and tmux (Homebrew on macOS, system package manager on Linux)
- Add the `tailmux` shell function
- On Linux, configure Tailscale operator access and enable Tailscale SSH
- Optionally install [Taildrive](#file-sharing-taildrive) shell functions

## Setup Commands

```bash
bash setup.sh install    # install/configure everything
bash setup.sh uninstall  # remove shell functions and optionally Tailscale state
bash setup.sh update     # check for and apply package updates
bash setup.sh --help     # show all options
```

All managed packages (`tailscale`, `tmux`, `davfs2`) track the latest stable version. Set `TAILMUX_TAILSCALE_TRACK=unstable` to follow the unstable channel.

## Usage

```bash
tailmux <host>            # connect and attach/create tmux session
tailmux doctor <host>     # run resolver diagnostics
tailmux --help            # show usage
tailmux --version         # show version
```

**Tip:** Use `tailscale status` to list all devices with their hostnames and IPs.

**Examples:**

```bash
tailmux macbook-pro       # connect by device name
tailmux 100.101.102.103   # connect by Tailscale IP
tailmux doctor home       # diagnose resolution for "home"
```

### Host Resolution Order

`tailmux` resolves hosts in this order to handle cases where short-name DNS is unreliable:

1. Direct IP input
2. User alias file (`~/.config/tailmux/hosts`)
3. `tailscale status --json` (device hostname / short name / FQDN)
4. `tailscale dns query` against your tailnet suffix
5. Optional LAN fallback (`<host>.local`) when `TAILMUX_LAN_FALLBACK=1`
6. System DNS lookup

### Alias File

- Path: `~/.config/tailmux/hosts` (override with `TAILMUX_HOSTS_FILE`)
- Format: `<alias> <target>`
- Example:
  ```text
  home 100.64.0.10
  mini mini.example-tailnet.ts.net
  ```

## File Sharing (Taildrive)

Share directories between devices using [Taildrive](https://tailscale.com/docs/features/taildrive):

```bash
tailshare myproject ~/projects/myapp     # share a directory
tailmount linux-laptop myproject         # mount on another machine
```

For ACL setup, commands reference, and macOS CLI details, see [docs/taildrive.md](docs/taildrive.md).

For troubleshooting connection issues, Tailscale on macOS, and Linux mounts, see [docs/troubleshooting.md](docs/troubleshooting.md).

## Supported Platforms

| OS | Package Manager | Remote Access Mode |
|----|-----------------|--------------------|
| macOS | Homebrew | OpenSSH (Remote Login) |
| Debian/Ubuntu | apt | Tailscale SSH (no OpenSSH required) |
| Fedora | dnf | Tailscale SSH (no OpenSSH required) |
| RHEL/CentOS | yum | Tailscale SSH (no OpenSSH required) |
| Arch Linux | pacman | Tailscale SSH (no OpenSSH required) |
| Windows | - | Use WSL |

## Uninstall

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ddv1982/tailmux/main/setup.sh) uninstall
```

## Notes

- Your tailnet ACLs must allow remote access for your chosen mode:
  - Linux default in this repo: Tailscale SSH policy
  - macOS / OpenSSH mode: network access to TCP port 22
- You can set simpler machine names in the [Tailscale admin console](https://login.tailscale.com/admin/machines) by clicking on a device and editing its name

## Development

`setup.sh` loads modules from `scripts/lib/`: `constants.sh`, `dependency_policy.sh`, `ui.sh`, `platform.sh`, `taildrive_templates.sh`, `rc_blocks.sh`, `managed_blocks.sh`, `package_manager.sh`, `tailscale_macos.sh`, `packages.sh`, `update.sh`, `install.sh`, `uninstall.sh`, `cli.sh`.

Run smoke tests:

```bash
bash scripts/tests/smoke.sh
```

For local module development:

```bash
TAILMUX_USE_LOCAL_MODULES=1 bash setup.sh install
```
