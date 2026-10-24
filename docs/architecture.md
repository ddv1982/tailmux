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
Ordinary installation publishes a staged executable and a three-line path-and-digest receipt, with the receipt published first for interrupted-install recovery.
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

Local `setup.sh install --replace-owned` replaces an unchanged receipt-owned executable under one prefix lifecycle lock.
It skips RC inspection and migration, including HOME and ZDOTDIR validation when an explicit prefix is supplied.
Ordinary install and uninstall retain their RC checks and recognized-block cleanup.
The published `install.sh` adapter is unchanged and does not use this replacement operation yet.

`inspect_installation` produces one result through `INSTALL_STATE`, `INSTALL_PREFIX`, `INSTALL_CURRENT_DIGEST`, `INSTALL_RECEIPT_DIGEST`, and `INSTALL_TRANSACTION`.
The receipt digest is the expected executable digest recorded in the receipt.
The states are `absent`, `owned`, `modified`, `receipt-only`, `foreign`, `unsafe`, and `pending`.
A missing or malformed receipt establishes no ownership. Symlinks, special files, unsafe metadata, and invalid transaction contents refuse mutation.
Lifecycle commands share this inspection. An existing lock always prevents a second writer.

Replacement stages the candidate on the prefix filesystem and verifies content backups in a private `.tailmux-backup.*` directory.
The backup contains `tailmux` and `receipt`. It remains after success or rollback and preserves content only.
The private `.tailmux-stage.*` directory retains `candidate` and `candidate-receipt` until completion.
Publication renames temporary copies over the public executable and receipt. It never unlinks the executable first.

The mode `0600` `.tailmux-transaction` record has exactly eleven LF-terminated lines in this order:

```text
tailmux-transaction-v1
id=<transaction-basename>
operation=<replace-owned-or-recover-modified>
phase=<prepared-or-binary-published-or-committed>
prefix-sha256=<digest-of-exact-prefix-bytes>
before-binary-sha256=<digest>
before-receipt-sha256=<digest-of-receipt-file>
after-binary-sha256=<digest>
after-receipt-sha256=<digest-of-receipt-file>
backup=<.tailmux-backup.basename>
stage=<.tailmux-stage.basename>
```

Digests are 64 lowercase hexadecimal characters. Basenames contain 1 through 96 ASCII letters, digits, dots, underscores, or hyphens, excluding `.` and `..`.
The parser bounds the current-user-owned regular record to 16 KiB, rejects NUL and noncanonical fields, and never evaluates data.
Stage and backup paths resolve directly under the caller's validated prefix and require separate metadata and digest checks.
The writer currently produces only `replace-owned` transactions. The grammar reserves `recover-modified` for later recovery work.

The `.tailmux-install-lock/owner` record is a current-user-owned mode `0600` regular file bounded to 256 bytes.
Its exact lines are `tailmux-lock-v1`, `uid=<decimal-current-uid>`, and `transaction=<transaction-basename>`, each terminated by LF.
Replacement and lock release require the matching owner record. No age or PID check removes a lock automatically.

`transaction_read`, `transaction_validate`, `transaction_write`, `transaction_publish`, and `transaction_restore_receipt_then_binary` expose the internal recovery operations.
Validation checks the public digests as well as the phase, backup, candidate, prefix binding, and any held lock owner.
Inspection, publication, rollback, and replacement under the lock validate the full prefix ancestry at their entry boundaries.
Each boundary scopes a `LIFECYCLE_CONTEXT` array containing that prefix and the detected platform.
Artifact checks traverse the remaining path below the validated prefix and still verify directory metadata, file ownership, links, mode, size, ACLs, and NUL rejection.
Calls without that context validate the full ancestry. The context ends with the operation and is not a persistent path cache.
Transaction receipt inspection can return both the recorded executable digest and the receipt content digest after one metadata check.
Recognized public pairs are old executable with old receipt, new executable with old receipt, and new executable with new receipt.
A rename can precede its phase update. An unknown digest, old executable with new receipt, or mismatched artifact refuses reconciliation.
Caught replacement errors and SIGTERM attempt verified rollback. Rollback restores the receipt before the executable, retaining a recognized pair if rollback itself stops.
Failed rollback preserves the transaction, stage, backup, and lock. SIGKILL also leaves pending evidence, which ordinary lifecycle commands refuse.
An interruption after transaction removal can leave an owned public pair and owner lock without a record.
That state requires owner inspection. Recovery limited to recognized pending transactions cannot validate a missing record or release that lock.
P1 exposes no resume, rollback, or abandoned-lock command.

The executable and receipt are separate renames, not one atomic commit.
Completion requires matching public contents before the transaction is removed and the lock is released.
Shell traps and content checks do not establish power-loss durability.
