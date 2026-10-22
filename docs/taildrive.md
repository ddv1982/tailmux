# File Sharing (Taildrive)

Share directories between Tailscale devices using [Taildrive](https://tailscale.com/docs/features/taildrive), Tailscale's built-in WebDAV file sharing. Useful for accessing project files on a remote machine with local editors and tools.

Both Linux and macOS can manage shares via CLI (`tailshare`, `tailshare-ls`) and mount shares (`tailmount`).

**Note for macOS:** This installer uses the open-source Homebrew `tailscale` formula (CLI-only, no menu bar icon) to enable full `tailscale drive` CLI support. If a standalone/App Store install is detected, setup stops and asks you to remove it first to avoid conflicts. If you prefer the GUI app, see [Tailscale macOS variants](https://tailscale.com/kb/1065/macos-variants), but note that GUI apps cannot use `tailscale drive` from the command line.

## Configure read-only access

This example lets `group:devs` read the named `myproject` share on devices tagged `tag:fileserver`.
Define that group and tag in your existing [Tailscale policy](https://login.tailscale.com/admin/acls), with only the intended readers and sharing devices.

Append these `nodeAttrs` entries to your existing array. They enable access for the readers and sharing for the file server.

```json
{
	"nodeAttrs": [
		{
			"target": ["group:devs"],
			"attr": ["drive:access"]
		},
		{
			"target": ["tag:fileserver"],
			"attr": ["drive:share"]
		}
	]
}
```

Append this application grant to your existing `grants` array.
Keep your existing network rules. This example adds no network grant.
Do not replace your complete policy or add duplicate top-level keys.
Existing broader grants can still permit additional access, so review them too.

```json
{
	"grants": [
		{
			"src": ["group:devs"],
			"dst": ["tag:fileserver"],
			"app": {
				"tailscale.com/cap/drive": [
					{ "shares": ["myproject"], "access": "ro" }
				]
			}
		}
	]
}
```

| Field | Example | Meaning |
|-------|---------|---------|
| `src` | `["group:devs"]` | Readers allowed by this grant |
| `dst` | `["tag:fileserver"]` | Devices that host the share |
| `shares` | `["myproject"]` | The permitted share name |
| `access` | `"ro"` | Read-only access |

To permit edits, change `"access": "ro"` to `"access": "rw"` for this named share.
Review the group's membership before granting write access.

After saving the policy, list your shares with `tailscale drive list`.
Test access from an intended reader before relying on the configuration.
See the [Taildrive docs](https://tailscale.com/docs/features/taildrive) and [application capability grants](https://tailscale.com/kb/1537/grants-app-capabilities) for policy details.

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

Explicit `mount_point` values must be absolute paths. Quote paths that contain spaces.
`tailmount` and `tailumount` reject empty, relative, and option-shaped values before running utilities.

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

After installation, authenticate and enable Tailscale SSH:
```bash
sudo tailscale up --ssh
```
