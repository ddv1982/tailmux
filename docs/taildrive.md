# File Sharing (Taildrive)

Core setup no longer installs, refreshes, or removes Taildrive helpers. It never installs mount dependencies or changes your Tailscale application.
Existing `tailshare`, `tailmount`, and related functions are legacy code pending retirement during the executable migration.
Their templates remain in `scripts/lib/taildrive_templates.sh` for review and regression tests, outside core setup.

## Remove a legacy installation

Back up your shell RC file and inspect the complete legacy Taildrive block against the reviewed template.
Remove only the recognized Taildrive span through your dotfile owner's workflow. Markers alone do not prove ownership.
Do not remove unrelated shell settings or a modified block without reviewing the changes.
Open a fresh shell to discard loaded helpers.

`bash setup.sh uninstall` removes recognized core Tailmux blocks only. It leaves Taildrive blocks, active mounts, shares, package installations, and Tailscale identity intact.
Ask the device operator to handle any remaining mounts or shares through the existing Taildrive installation.
Package removal and application migration remain separate operator decisions.

## Use existing legacy helpers

The command reference below describes an existing legacy installation. It is not a core setup option.
Legacy mount helpers can retry through `sudo`. Do not invoke them unless you intend that separate operation.
For macOS CLI availability, consult the documentation for your existing [Tailscale variant](https://tailscale.com/docs/concepts/macos-variants).
Core setup neither selects a variant nor changes it.

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

Linux mounting requires an operator-managed `davfs2` installation. Core setup never installs it.
Keep dependency, daemon, sharing, and authentication management with their existing owners.
