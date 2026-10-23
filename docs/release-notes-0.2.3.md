# v0.2.3

Tailmux can use an explicitly selected Tailscale daemon through `TAILMUX_TAILSCALE_SOCKET`.
Set it once to the daemon's absolute socket path. Diagnostics, peer discovery, and SSH then use the same endpoint.
This helps Mac users running both the Tailscale app and a separate CLI service.

Doctor identifies the selected endpoint. An unavailable explicit endpoint fails without trying another daemon.
Unset the variable to keep Tailscale's default selection.
See [daemon selection](usage.md#select-a-tailscale-daemon) for setup.

The release retains the remaining live platform acceptance gaps documented in [compatibility](compatibility.md).
