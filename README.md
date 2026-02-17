# tailmux

Access tmux sessions on your Tailscale devices from anywhere.

## Quick Start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ddv1982/tailmux/main/setup.sh)
```

This will prompt you to:
- Install Homebrew (macOS only, if not already installed)
- Install Tailscale
- Install tmux
- Add the `tailmux` command to your shell
- On Linux, configure Tailscale operator access for your current user (so `tailscale up` works without `sudo`)
- On Linux, enable Tailscale SSH on this device (`tailscale set --ssh`)
- Optionally install Taildrive (`tailshare`/`tailmount`) shell functions
- On Linux, optionally install `davfs2` when enabling Taildrive mounts

Before connecting, make sure remote access is enabled on the destination:
- macOS: System Settings → General → Sharing → Remote Login
- Linux: `sudo tailscale up --ssh` (no OpenSSH daemon required)

## Dependency Version Policy

Dependency upgrade policy is centralized in:

- `scripts/lib/dependency_policy.sh`

Edit that file to control Tailscale upgrades from one place:

```bash
# Default track
TAILMUX_TAILSCALE_TRACK=stable

# Pin Linux to an exact version
TAILMUX_TAILSCALE_VERSION=1.94.1

# Or leave empty to install the latest version in the selected track
TAILMUX_TAILSCALE_VERSION=
```

Notes:
- Linux installs use `TRACK` and `TAILSCALE_VERSION` from this policy file.
- Re-run `setup.sh install` after changing policy values to reconcile an existing install.
- macOS remains on Homebrew `tailscale` formula latest in this phase.
- Optional manual macOS hold on one machine: `brew pin tailscale` (undo with `brew unpin tailscale`).

## Usage

```bash
tailmux <host>
tailmux doctor <host>
```

Connects to the host over Tailscale and attaches to an existing tmux session (or creates a new one).

- `hostname` - Tailscale device name or IP
- `doctor` - run resolver diagnostics for a host

**Tip:** Use `tailscale status` to list all devices with their hostnames and IPs - handy for troubleshooting connection issues.

**Examples:**

```bash
tailmux macbook-pro       # connect by device name
tailmux 100.101.102.103   # connect by your Tailscale IP (from `tailscale status`)
tailmux doctor home       # diagnose host resolution path for `home`
```

### DNS-robust host resolution

`tailmux` resolves hosts in this order to reduce breakage when short-name DNS is unreliable on some macOS/Tailscale combinations:

1. Direct IP input
2. `tailscale status --json` (device hostname / short name / FQDN)
3. `tailscale dns query` against your tailnet suffix
4. Optional LAN fallback (`<host>.local`) when `TAILMUX_LAN_FALLBACK=1`
5. System DNS lookup

Optional alias file:

- Path: `~/.config/tailmux/hosts` (override with `TAILMUX_HOSTS_FILE`)
- Format: `<alias> <target>`
- Example:
  ```text
  home 100.64.0.10
  mini mini.example-tailnet.ts.net
  ```

## File Sharing (Taildrive)

Share directories between Tailscale devices using [Taildrive](https://tailscale.com/docs/features/taildrive), Tailscale's built-in WebDAV file sharing. Useful for accessing project files on a remote machine with local editors and tools.

Both Linux and macOS can manage shares via CLI (`tailshare`, `tailshare-ls`) and mount shares (`tailmount`).

**Note for macOS:** This installer uses the open-source Homebrew `tailscale` formula (CLI-only, no menu bar icon) to enable full `tailscale drive` CLI support. If a standalone/App Store install is detected, setup now stops and asks you to remove it first to avoid conflicts. If you prefer the GUI app, see [Tailscale macOS variants](https://tailscale.com/kb/1065/macos-variants), but note that GUI apps cannot use `tailscale drive` from the command line.

### One-Time Taildrive ACL Setup

Taildrive requires two things in your [Tailscale ACL policy](https://login.tailscale.com/admin/acls): `nodeAttrs` to enable the feature, and a grant to define who can access which shares. Open the [Access Controls](https://login.tailscale.com/admin/acls) page and add/merge the sections below.

Add the following to your ACL policy. If your policy already has `nodeAttrs` or `grants`, merge the entries into the existing arrays — do not add duplicate top-level keys.

<details>
<summary>Add to <code>nodeAttrs</code></summary>

```jsonc
{
  // Any device can access shared directories with Taildrive
  "target": ["*"],
  "attr": ["drive:access"]
},
{
  // Only tailnet admins can use Taildrive to share directories
  "target": ["autogroup:admin"],
  "attr": ["drive:share", "drive:access"]
}
```

- `drive:share` — permission to create and manage shared folders
- `drive:access` — permission to access shared folders from other devices

</details>

<details>
<summary>Add to <code>grants</code></summary>

Your `grants` array likely already has `ip`-based network grants. The Taildrive entry uses `app` instead of `ip` — they don't overlap, so keep your existing entries and append the Taildrive grant:

```jsonc
"grants": [
    // your existing network grants
    {
        "src": ["*"],
        "dst": ["*"],
        "ip":  ["*"],
    },
    {
        "src": ["autogroup:member"],
        "dst": ["autogroup:member"],
        "ip":  ["*"],
    },
    // Taildrive: members can read/write all shares on their own devices
    {
        "src": ["autogroup:member"],
        "dst": ["autogroup:self"],
        "app": {
            "tailscale.com/cap/drive": [
                { "shares": ["*"], "access": "rw" }
            ]
        }
    },
],
```

</details>

<details>
<summary>Customize the Taildrive grant</summary>

| Field | Example | Description |
|-------|---------|-------------|
| `src` | `["autogroup:member"]`, `["group:devs"]` | Who can access |
| `dst` | `["autogroup:self"]`, `["tag:fileserver"]`, `["*"]` | Whose shares to access |
| `shares` | `["*"]`, `["projects", "docs"]` | Which share names (`*` = all) |
| `access` | `"rw"`, `"ro"` | Read-write or read-only |

</details>

After saving the policy, verify with:

```bash
tailscale drive list
```

See the [Taildrive docs](https://tailscale.com/docs/features/taildrive) and [grants app capabilities](https://tailscale.com/kb/1537/grants-app-capabilities) for more details.

### Usage

```bash
# On the machine with your files (e.g. Linux laptop):
tailshare myproject ~/projects/myapp     # share a directory
tailshare-ls                             # list active shares

# On another machine (macOS or Linux):
tailmount linux-laptop myproject         # mount the share
# → Mounted at ~/taildrive/linux-laptop/myproject

tailmount-ls                             # list mounted shares
tailumount linux-laptop myproject        # unmount
```

```bash
# Stop sharing when done:
tailunshare myproject
```

### Finding Host and Share Names

If you are unsure which host/share token to use with `tailmount`, list what Taildrive currently exposes (run this on a Linux machine, or any machine where `tailscale drive` is available):

```bash
tailscale drive list
```

Use the exact `<host>/<share>` values shown there in `tailmount <host> <share>`.

### Share Name Guidelines

Taildrive share names should be simple and portable:

- Prefer letters, numbers, and underscores.
- Avoid spaces and special punctuation in share names.
- If you see `invalid share`, choose a simpler name and try again.

### Commands

| Command | Description |
|---------|-------------|
| `tailshare <name> [path]` | Share a directory (defaults to `.`) |
| `tailunshare <name>` | Stop sharing |
| `tailshare-ls` | List active shares |
| `tailmount <host> <share> [mount_point]` | Mount a share on macOS/Linux (defaults to `~/taildrive/<host>/<share>`) |
| `tailumount <host> <share> [mount_point]` | Unmount a share |
| `tailmount-ls` | List mounted shares |

**Linux prerequisite:** Linux mounting uses `davfs2` (`mount -t davfs`). The installer can prompt to install it automatically when you enable Taildrive functions.

### macOS: Open-Source Tailscale (CLI-only)

On macOS, this installer uses the Homebrew `tailscale` formula — the open-source CLI-only version. This enables full `tailscale drive` CLI support but has some trade-offs:

| Feature | Open-Source (Homebrew) | GUI App (Standalone/App Store) |
|---------|------------------------|--------------------------------|
| Menu bar icon | No | Yes |
| `tailscale drive` CLI | **Yes** | No |
| Auto-configured MagicDNS | Manual | Auto |
| Manage via | Terminal commands | GUI + limited CLI |

**Common commands:**
```bash
tailscale status          # Check connection status
tailscale up              # Connect to tailnet
tailscale down            # Disconnect
tailscale drive list      # List shares
```

After installation, authenticate once with:
```bash
tailscale up
```

On Linux, include `--ssh`:
```bash
sudo tailscale up --ssh
```

### Troubleshooting Tailscale on macOS

- **"tailscale: command not found"**: Ensure Homebrew's bin is in your PATH (`brew shellenv`), then run `brew link tailscale` to recreate CLI symlinks if needed.
- **"Is Tailscale running?"**: Start the daemon with `sudo brew services start tailscale` (sudo required for root privileges).
- **"failed to connect to local Tailscale service"**: Restart daemon with `sudo brew services restart tailscale`. If it still fails, remove stale artifacts and retry:
  - `rm -f /opt/homebrew/var/log/tailscaled.log`
  - `rm -f ~/Library/LaunchAgents/homebrew.mxcl.tailscale.plist`
  - `sudo rm -f /Library/LaunchDaemons/homebrew.mxcl.tailscale.plist`
  - `sudo brew services start tailscale`
- **Authentication**: Run `tailscale up` to authenticate (opens browser). If you hit a permissions error, retry with `sudo tailscale up`.
- **Name resolves by IP only / short hostnames fail**:
  - Run: `tailmux doctor <hostname>`
  - Run: `tailscale dns status --all`
  - If needed, use `TAILMUX_LAN_FALLBACK=1` or add a stable alias in `~/.config/tailmux/hosts`
- **Switching from GUI app**: Setup can auto-remove Homebrew cask installs during migration. Standalone/App Store installs must be removed from Applications before setup will install the Homebrew formula.
- See: [Taildrive docs](https://tailscale.com/kb/1369/taildrive) and [macOS variants](https://tailscale.com/kb/1065/macos-variants)

### Troubleshooting Linux Mounts

- If `tailmount` fails with `mount.davfs` missing, install `davfs2`:
  - Debian/Ubuntu: `sudo apt-get update -y && sudo apt-get install -y davfs2`
  - Fedora: `sudo dnf install -y davfs2`
  - RHEL/CentOS: `sudo yum install -y davfs2`
  - Arch: `sudo pacman -S --noconfirm davfs2`
- If mount/unmount requires elevated privileges, `tailmount`/`tailumount` will retry with `sudo`.

## Uninstall

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ddv1982/tailmux/main/setup.sh) uninstall
```

## Supported Platforms

| OS | Package Manager | Remote Access Mode |
|----|-----------------|--------------------|
| macOS | Homebrew | OpenSSH (Remote Login) |
| Debian/Ubuntu | apt | Tailscale SSH (no OpenSSH required) |
| Fedora | dnf | Tailscale SSH (no OpenSSH required) |
| RHEL/CentOS | yum | Tailscale SSH (no OpenSSH required) |
| Arch Linux | pacman | Tailscale SSH (no OpenSSH required) |
| Windows | - | Use WSL |

## Notes

- Your tailnet ACLs must allow remote access for your chosen mode:
  - Linux default in this repo: Tailscale SSH policy
  - macOS / OpenSSH mode: network access to TCP port 22
- You can set simpler machine names in the [Tailscale admin console](https://login.tailscale.com/admin/machines) by clicking on a device and editing its name

## Development

`setup.sh` is a thin entrypoint that loads modules from `scripts/lib`:

- `constants.sh`
- `dependency_policy.sh`
- `ui.sh`
- `platform.sh`
- `taildrive_templates.sh`
- `rc_blocks.sh`
- `managed_blocks.sh`
- `package_manager.sh`
- `tailscale_macos.sh`
- `packages.sh`
- `install.sh`
- `uninstall.sh`
- `cli.sh`

Run smoke tests:

```bash
bash scripts/tests/smoke.sh
```

By default, `setup.sh` fetches the latest module set from GitHub `main`. For local module development, set:

```bash
TAILMUX_USE_LOCAL_MODULES=1 bash setup.sh install
```
