# Client architecture reference

`bin/tailmux` is the single installed runtime file.
It runs under Bash 3.2 or later and contains its private jq filter.
It never loads setup modules or shell startup files.

One immutable command array holds the PATH-resolved `tailscale` invocation and optional global socket argument.
One effective socket and source selection feeds that array for all version probes, status reads, and SSH.
An explicitly set `TAILMUX_TAILSCALE_SOCKET` wins, including invalid or empty values, which fail before daemon access.
A valid override bypasses lower-priority config reads. Otherwise saved config wins, then the native CLI default when the config is absent.
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
| SavedSocket | Bash indexed record `saved_socket` with state, literal socket, and diagnostic. States are `absent`, `valid`, `malformed`, `unknown`, and `unsafe` |
| EffectiveSocket | One literal value and source, either `environment`, `saved`, or `native default` |
| Request | `connect` or `doctor`, selector, optional user, `tailscale-ssh`, `attach-any` |
| Snapshot | Backend, current tailnet suffix, peer stable IDs, canonical DNS, advertised addresses, `sshHostKeys`, `InNetworkMap`, advisory `Online`, optional `Expired` defaulting to false |
| ResolvedTarget | One stable peer identity, canonical DNS, chosen advertised address, optional user |
| Failure | One named error with no transport invocation |

`$HOME/.config/tailmux/config` has exactly two LF-terminated records, `tailmux-config-v1` and `socket=/absolute/path`.
The 8 KiB boundary rejects NUL, ASCII controls in the socket, extra records, and missing final LF.
Spaces, Unicode, and shell punctuation remain literal. No runtime Python or additional installed artifact is involved.
The existing hosts path remains unchanged.

The config reader refuses symlinks at the file and every ancestor, even for user-owned dotfiles links.
It checks regular type before opening and requires current-user ownership, one hard link, mode `0600`, bounded size, and supported metadata.
Ancestry requires root or current-user ownership. HOME and its config directories require current-user ownership and no group or other writes.
Only root-owned sticky ancestors may be group or other writable.
Batched `stat` and `ls` calls validate metadata and ACLs for all extant components in each read.
On macOS, these calls use `/usr/bin/stat` and `/bin/ls` so GNU tools earlier in PATH cannot change their flag semantics.
Unknown or mutating ACLs are refused. The exact macOS directory ACL `group:everyone deny delete` is accepted.
File flags on macOS must be zero. Root directory flags do not establish config ownership.
A bounded `head` and `tr` pipeline maps NUL to a rejected control byte before parsing.
The reader checks pipeline status and byte count before parsing, including successful empty utility output.
Command substitution retains final LF with a sentinel. Process substitution does not carry producer success across the boundary.
Absent state comes only from filesystem inspection, never empty tool output or an empty hash.
The trust model excludes adversarial concurrent changes by the same UID or root.

`--config` commands dispatch before effective connection parsing. Positional `config` remains a selector.
Show reports both saved and effective state and resolves the CLI through PATH without invoking it.
Set and reset do not need transport dependencies. All config-command failures bypass optional Sentry reporting.
Ordinary connection and doctor failure reporting is unchanged.

One per-user `$HOME/.config/tailmux/.config-lock` directory excludes concurrent writers.
The writer arms cleanup immediately after successful lock acquisition, before further fallible work.
Unknown existing locks and SIGKILL remnants remain fail-closed. There is no PID or stale-age unlock.
New directories use a private umask. Mode `0600` staged data publishes by same-directory rename after content and metadata checks.
Reads observe an old or complete new record and do not acquire the writer lock.
Reset verifies a mode `0600` content backup beside the config before unlinking safe current-version data, including malformed data.
Unknown versions, unsafe metadata, links, and oversized data refuse reset and set without discarding the original.
Backup content comparison checks the producer exit status directly and does not rely on process substitution or digest output.
Caught failures clean up the current writer's unpublished stage and lock when possible.
Publication can complete before a later failure is reported. Shell traps do not promise power-loss durability.
Lifecycle operations preserve config and hosts. Saved settings never require shell startup edits.
See [daemon selection](usage.md#select-a-tailscale-daemon) for command and repair examples.

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
The public `install.sh update` authenticates the package and delegates to this operation for an existing regular client.
When the executable is absent, it uses ordinary installation, including valid same-source receipt-only recovery.

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
One replacement writer produces both `replace-owned` and `recover-modified` transactions.
Recovery requires a modified safe executable, a structurally valid path-bound receipt, and exact approval of the observed executable digest.
It preserves the receipt's original bytes without changing its expected digest to authorize the modified executable.

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
Reviewed local setup exposes guarded resume, rollback, and abandoned-lock maintenance for recognized pending transactions.

The setup parser produces one `RecoveryRequest` indexed record, `RECOVERY_REQUEST`, with action, expected current digest, and transaction identity.
Its mutually exclusive actions are `dry-run`, `apply`, `resume`, `rollback`, and `unlock-abandoned`.
Preview accepts no approval or transaction. Apply requires the digest and no transaction.
Maintenance requires both the digest and exact transaction ID. Invalid and duplicate arguments fail before effects.
No runtime positional command or installed module is added.

Preview reads P1 classification and candidate content identity without Git or installed-client execution.
Its source path identifies local input and makes no publisher-authenticity claim.
The candidate's offline config handler reports effective configuration and provenance without changing it.
Malformed configuration is reported separately and is never silently repaired by recovery.
Local `configure --socket` delegates directly to that candidate's config writer without a lifecycle prefix operation.

Recovery apply uses the same stage, backup verification, transaction publication, rollback helpers, and lock as clean-owned replacement.
It rechecks approval, receipt contents, and metadata after acquiring the lock.
Only an already-owned pair matching the actual candidate can bypass replacement approval as a read-only completed retry.
A different owned version remains an ordinary `install --replace-owned` operation.

Maintenance validates the exact prefix, transaction schema and identity, owner record, approved current digest, stage and backup hashes, and recognized public pair.
Resume additionally binds the staged binary to the actual reviewed candidate digest, not just the record's self-declared after digest.
Pre-publication resume guards run before the replacement rollback trap is armed.
Rollback restores previous local history without authenticating it.
Explicit abandoned-lock release asserts that no writer remains active and only removes a fully validated matching pending transaction's lock.
It does not publish or resume. Resume and rollback subsequently acquire the ordinary lock with the same transaction identity and revalidate.
Unknown, malformed, recordless, and completed-cleanup locks remain owner-inspection cases.

The executable and receipt are separate renames, not one atomic commit.
Completion requires matching public contents before the transaction is removed and the lock is released.
Shell traps and content checks do not establish power-loss durability.
