# File Sharing (Taildrive)

Share directories between Tailscale devices using [Taildrive](https://tailscale.com/docs/features/taildrive), Tailscale's built-in WebDAV file sharing. Useful for accessing project files on a remote machine with local editors and tools.

Both Linux and macOS can manage shares via CLI (`tailshare`, `tailshare-ls`) and mount shares (`tailmount`).

**Note for macOS:** This installer uses the open-source Homebrew `tailscale` formula (CLI-only, no menu bar icon) to enable full `tailscale drive` CLI support. If a standalone/App Store install is detected, setup stops and asks you to remove it first to avoid conflicts. If you prefer the GUI app, see [Tailscale macOS variants](https://tailscale.com/kb/1065/macos-variants), but note that GUI apps cannot use `tailscale drive` from the command line.

## One-Time ACL Setup

Taildrive requires two things in your [Tailscale ACL policy](https://login.tailscale.com/admin/acls): `nodeAttrs` to enable the feature, and a grant to define who can access which shares. Open the [Access Controls](https://login.tailscale.com/admin/acls) page and add/merge the sections below.

If your policy already has `nodeAttrs` or `grants`, merge the entries into the existing arrays — do not add duplicate top-level keys.

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

## Usage

```bash
# On the machine with your files (e.g. Linux laptop):
tailshare myproject ~/projects/myapp     # share a directory
tailshare-ls                             # list active shares

# On another machine (macOS or Linux):
tailmount linux-laptop myproject         # mount the share
# -> Mounted at ~/taildrive/linux-laptop/myproject

tailmount-ls                             # list mounted shares
tailumount linux-laptop myproject        # unmount
```

```bash
# Stop sharing when done:
tailunshare myproject
```

### Finding Host and Share Names

If you are unsure which host/share token to use with `tailmount`, list what Taildrive currently exposes:

```bash
tailscale drive list
```

Use the exact `<host>/<share>` values shown there in `tailmount <host> <share>`.

### Share Name Guidelines

Taildrive share names should be simple and portable:

- Prefer letters, numbers, and underscores.
- Avoid spaces and special punctuation in share names.
- If you see `invalid share`, choose a simpler name and try again.

## Commands

| Command | Description |
|---------|-------------|
| `tailshare <name> [path]` | Share a directory (defaults to `.`) |
| `tailunshare <name>` | Stop sharing |
| `tailshare-ls` | List active shares |
| `tailmount <host> <share> [mount_point]` | Mount a share on macOS/Linux (defaults to `~/taildrive/<host>/<share>`) |
| `tailumount <host> <share> [mount_point]` | Unmount a share |
| `tailmount-ls` | List mounted shares |

**Linux prerequisite:** Linux mounting uses `davfs2` (`mount -t davfs`). The installer can prompt to install it automatically when you enable Taildrive functions.

## macOS: Open-Source Tailscale (CLI-only)

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
