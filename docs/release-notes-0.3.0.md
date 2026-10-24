# v0.3.0

Save a Tailscale daemon socket with `tailmux --config set socket PATH`.
Fresh shells then use that selection for diagnostics, peer discovery, and SSH.
An explicit `TAILMUX_TAILSCALE_SOCKET` override still takes precedence.

Reviewed local setup can preview and recover a modified client when you approve its exact current digest.
Recovery verifies and retains the original executable and receipt in a private backup.
Unknown or unsafe installations remain protected.
Recognized interrupted transactions support explicit lock release, resume, and rollback.
Owned updates use the same transaction writer without removing the executable first.

Use candidate `configure --socket PATH` to save a socket before replacing an older client.
Recovery never executes the installed wrapper or edits shell startup files.
See [recovery instructions](usage.md#recover-a-modified-client-from-a-reviewed-checkout) and [transaction maintenance](troubleshooting.md#resume-or-roll-back-a-recognized-pending-transaction).

The public installer and README pins change separately after authenticated assets are available.
Live SSH coverage remains [not verified](compatibility.md).
