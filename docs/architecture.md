# Client architecture reference

`bin/tailmux` is the single installed runtime file.
It runs under Bash 3.2 or later and contains its private jq filter.
It never loads setup modules or shell startup files.

One immutable command array holds the PATH-resolved `tailscale` invocation and optional global socket argument.
`TAILMUX_TAILSCALE_SOCKET` selects an absolute local socket path for all version probes, status reads, and SSH.
Unset configuration retains Tailscale's default selection. Invalid explicit configuration fails before daemon access.
An unavailable selected endpoint never triggers a retry through the default daemon.
Doctor reports endpoint selection without discovering other installations or changing services.

Optional Sentry error reporting is enabled only by `TAILMUX_SENTRY_DSN`.
The explicit failure handler sends fixed categories for missing dependencies, daemon failures,
invalid status data, and local I/O failures. It includes a relative source location,
release, and environment, with no request, device, host, shell environment, or diagnostic text.
HTTPS delivery through optional curl has a three-second limit and cannot replace the original failure status.
No reporting traps wrap the transport: `exec tailscale ssh` and its exit/signal behavior remain intact.
See [monitoring configuration](usage.md#optional-sentry-error-reporting).

| Record | Fields |
| --- | --- |
| Request | `connect` or `doctor`, selector, optional user, `tailscale-ssh`, `attach-any` |
| Snapshot | Backend, current tailnet suffix, peer stable IDs, canonical DNS, advertised addresses, `sshHostKeys`, `InNetworkMap`, advisory `Online`, optional `Expired` defaulting to false |
| ResolvedTarget | One stable peer identity, canonical DNS, chosen advertised address, optional user |
| Failure | One named error with no transport invocation |

The jq boundary requires exactly one JSON document and validates every visible peer.
It bounds status to 8 MiB, peer count to 4,096, each address and key array to 64 entries, and each public-key record to 16 KiB.
Alias input is bounded to 64 KiB and 256 entries.
It rejects raw NUL bytes and incompatible field types.
`Peer:null` means no peers.

Selection uses only `InNetworkMap:true` peers with a canonical DNS name and advertised addresses.
Short selectors require the current tailnet suffix.
The selected DNS name and every address of that peer must be unique across all visible peer identities.
Duplicate stable IDs invalidate the snapshot.
Explicit address requests retain that address.
Name requests choose IPv4 before IPv6, then use lexical order within the family.
Public-key validation checks single-line structure only. SSH performs cryptographic verification.

The sole transport call expands that same command array:

```bash
exec "${tailscale_cmd[@]}" ssh "$validatedUserAndChosenAddress" -t "$constantRemoteProgram"
```

The fixed remote program discovers tmux through the remote account, runs `tmux attach || tmux new`, and exits 127 if tmux is missing.
No local PATH, selector, alias, username, or session string enters that program.
The wrapper owns host-key verification and transport errors.
Preflight does not pin a persistent ID atomically across the wrapper's fresh coordination lookup.

`setup.sh` uses only local lifecycle modules.
Help and version dispatch before those modules load.
Installation publishes a staged executable and a three-line path-and-digest receipt, with the receipt published first for interrupted-install recovery.
The receipt establishes local ownership, not publisher authenticity.
On macOS, RC migration removes only recognized byte spans after fingerprint, flag, xattr, and metadata checks.
On Linux, migration uses GNU cp with all-attribute preservation, checks inode flags with lsattr, and compares extended-attribute digests through isolated Python 3.
Only ordinary inode flags (none or extent format) are supported; other flags and unavailable metadata inspection cause refusal before lifecycle writes.
Fresh Linux lifecycle operations need no RC migration.
Unmanaged RC data remains opaque.
Protected macOS RC backups precede replacement, and content and metadata are checked after publication.
Backups of receipt-owned client artifacts preserve content only.
A lifecycle failure can leave verified partial progress and returns nonzero.
No package, service, authentication, policy, or release operation belongs to these modules.
