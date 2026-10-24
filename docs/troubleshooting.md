# Troubleshoot the client

Run the printed absolute executable path if an existing shell alias or function shadows `tailmux`.
Setup preserves unmanaged shell code and does not modify your current shell.

```bash
"$HOME/.local/bin/tailmux" --version
"$HOME/.local/bin/tailmux" doctor
"$HOME/.local/bin/tailmux" doctor device-name
```

Doctor with a selector reports the selected identity and address without connecting.
Success does not prove SSH access or remote tmux readiness.
Doctor without a selector lists local dependencies. Read the reported classifications. Exit status zero does not mean every dependency is ready.

| Failure | Action |
| --- | --- |
| `missing-dependency` | Install the named tool through its existing package owner. |
| `invalid-config` | Set `TAILMUX_TAILSCALE_SOCKET` to an absolute path without control characters, or unset it for Tailscale's default selection. |
| `daemon-unavailable` | Check the selected daemon and socket. With multiple installations, [select the intended daemon](usage.md#select-a-tailscale-daemon). No fallback connection was started. |
| `logged-out` | Ask the machine owner to restore the intended identity. Tailmux never logs in or out for you. |
| `stopped/not-ready` | Check that Tailmux uses the intended daemon, then resolve that daemon's readiness state. |
| `invalid-schema` | Use a reviewed compatible status schema. Do not replace jq with a text parser. |
| `invalid-aliases` | Use exactly two fields per entry and canonical full-name or advertised-address targets. |
| `unknown-selector` | Copy a canonical name or address from your known peer inventory. Shared peers need a full name or explicit canonical alias. |
| `ambiguous-selector` | Resolve the duplicate identity name or address in the coordination inventory. Tailmux never chooses the first record. |
| `missing-advertised-host-keys` | Follow [the host-key recovery steps](#resolve-missing-advertised-host-keys). |
| `peer-key-expired` | Have the destination owner renew its intended node identity. Tailmux does not renew it or infer expiry from dates. |

`Online:false` alone does not prevent a connection.
IPv6 accepts the advertised spelling, ignoring hexadecimal case.
Alternate compressed spellings are not normalized.
When the current tailnet suffix is unavailable or invalid, use a full canonical name or advertised address.

The App Store and TestFlight Tailscale variants do not expose `tailscale ssh`.
Tailmux propagates that wrapper error and does not replace the app or retry with ordinary SSH.
Wrapper errors, remote exit codes, and policy failures propagate through `exec`.
A remote account without tmux exits 127.
See [remote tmux discovery](#resolve-tmux-not-found-on-remote).

## Resolve tmux not found on remote

A local `tmux -V` check on the destination does not prove that an SSH command can find tmux.
After Tailscale SSH setup, run this from your client with the intended destination account:

```bash
tailscale ssh user@device-name -t 'printf "%s\n" "$PATH"; command -v tmux && tmux -V'
```

The output should include the remote PATH, tmux executable path, and version.
If tmux is missing, install it in a directory on that remote PATH or configure the destination's SSH command environment to include its directory.
An alias or PATH setting loaded only by an interactive shell is insufficient.

## Resolve missing-advertised-host-keys

Tailscale did not provide SSH host keys for the selected device. Tailmux stopped before connecting.
The destination may not have Tailscale SSH enabled, or the access policy may prevent key distribution.

1. Confirm that the destination has Tailscale SSH enabled. Follow [Prepare the destination](usage.md#prepare-the-destination) if setup is incomplete.
2. Have your tailnet administrator check network access to destination port 22 and SSH access for your intended destination account.
3. On your client, retry the selection check:

   ```bash
   "$HOME/.local/bin/tailmux" doctor device-name
   ```

4. When the check succeeds, retry the connection:

   ```bash
   "$HOME/.local/bin/tailmux" device-name
   ```

An ordinary SSH server does not supply the host keys that `tailscale ssh` requires.
Keep host-key verification enabled.

## Resolve lifecycle refusals

Ordinary setup accepts only absolute HOME, ZDOTDIR, and prefix paths without line breaks.
Spaces are supported.
It refuses unsafe writable ancestors, unexpected ACLs, unsupported metadata, ambiguous ownership, and symlinked writes.
The current user and root remain trusted owners.
These checks do not protect against a malicious process with the same UID or root privileges.

An unrelated symlinked RC can remain unchanged.
If a symlinked RC contains a legacy managed block, remove that exact block through your dotfiles owner and retry.
Unknown bodies or malformed markers require manual inspection.
Do not delete a block merely because its marker mentions Tailmux.

Automatic legacy RC migration supports macOS and Linux when metadata can be verified.
Linux needs GNU cp, lsattr, and Python 3. Unsupported inode flags, ACLs, and failed metadata reads still require manual migration.
The published v0.2.0 package rejects Linux legacy markers; that release requires manual block removal through your dotfiles owner, followed by install or uninstall retry.
Back up the RC file and remove only the recognized Tailmux marker span; keep unrelated shell content.
Linux fresh installation and uninstall remain usable when no managed RC block needs changing.

A recognized macOS removal saves `.tailmux-backup.*/original` beside the RC before publication.
The backup directory is private and retains the original metadata.
Executable removal saves protected content-only backups under the selected prefix.
Those owned-client backups do not promise flag, xattr, or other metadata preservation.
Keep these backups until you have checked the migration.

Interrupted receipt-first publication can leave a receipt without an executable.
Retry the same reviewed source and prefix, or run uninstall to remove that owned receipt.
A pre-existing executable without a valid receipt remains foreign and requires manual inspection.
An interruption can also leave a lifecycle lock or stage directory. Preserve these artifacts for inspection.
Setup never clears a lock automatically, even if it appears old or its original process has exited.
A failed migration can leave the verified executable installed and some recognized blocks already removed.
The error remains nonzero. Retry after resolving the reported cause.
No lifecycle failure is reported as complete.

## Recover a modified client

The recovery interface requires v0.3.0. Obtain the verified command from the [README](../README.md#install-update-or-uninstall).

With the v0.3.0 verified README command, replace `install` on its last line with the arguments shown below.
Keep every download and checksum-verification line unchanged. Each invocation authenticates the pinned installer and package before running packaged setup.
Help is offline. Public recovery preview, recovery application, and configuration need network access.

If the old client contains a socket workaround, save the intended socket explicitly before replacement:

```text
configure --socket /var/run/tailscaled.socket
```

Use the socket supplied by your Tailscale installation. The example path is not a universal default.
Configuration works before installation, accepts no prefix, and runs only the authenticated package's candidate handler.
It never executes the installed old wrapper or creates an executable prefix.
Configuration is a separate operation. Executable rollback does not undo it.

Preview without changing the installation, saved settings, or shell files:

```text
recover --prefix "$HOME/.local/bin" --dry-run
```

The preview prints the classification, absolute prefix, observed current executable SHA256, receipt's expected executable digest, candidate version and digest, and extracted source path.
The public adapter establishes publisher authenticity before that local setup preview runs.
The preview's own local-content disclaimer describes the setup layer alone.
Its effective socket and provenance come from the candidate's scrubbed environment. Public commands do not inherit `TAILMUX_TAILSCALE_SOCKET`.
The [installed runtime's environment precedence](usage.md#select-a-tailscale-daemon) applies when you run that runtime directly.
Malformed configuration needs separate inspection or explicit repair. Recovery preserves it.

An absent prefix uses ordinary `install`. A valid receipt without an executable can be retried only with the same source and prefix.
An unchanged receipt-owned executable uses `update`, which shares the canonical replacement operation under one lifecycle lock.
A safe modified executable with a valid path-bound receipt needs exact-digest approval.
Missing or malformed receipts establish no ownership. Foreign content, unsafe metadata, links, FIFOs, and unknown locks remain protected.
There is no force-overwrite option.

For a modified client, replace `LOWER64HEX` with the exact 64 lowercase hexadecimal characters from the preview:

```text
recover --prefix "$HOME/.local/bin" --expect-current-sha256 LOWER64HEX
```

Recovery rechecks the executable, receipt, and metadata under the lifecycle lock. A changed digest causes refusal.
It saves and verifies the exact modified executable and original receipt under a private `.tailmux-backup.*` directory in the prefix.
The preview's `.tailmux-backup.XXXXXX` suffix is a pattern. Setup chooses its random name only during application.
These backups preserve content only. They record local history and do not authenticate an old release.
Recovery never parses the old wrapper, infers its socket, rewrites its receipt to authorize old bytes, or edits shell startup files.
Repeating application after the candidate and receipt are installed makes no changes or duplicate backups, even with the original approval digest.

Local alternatives use the same reviewed source and writer:

```bash
bash setup.sh configure --socket /var/run/tailscaled.socket
bash setup.sh recover --prefix "$HOME/.local/bin" --dry-run
bash setup.sh recover --prefix "$HOME/.local/bin" --expect-current-sha256 LOWER64HEX
```

Local setup is offline and needs independent source review. A receipt or local digest does not establish publisher authenticity.

## Replace an unchanged owned client from a reviewed checkout

The v0.3.0 public `update` action authenticates the package, then uses this shared replacement operation for an existing regular owned client:

```bash
/bin/bash setup.sh install --replace-owned --prefix "$HOME/.local/bin"
```

The executable must match its valid receipt. Replacement skips RC inspection and migration.
Unknown legacy blocks or an unrelated ZDOTDIR do not block replacement.
Use ordinary `install` for a fresh prefix or receipt-only recovery.
Same-source update is a no-op. Successful replacement retains a private `.tailmux-backup.*` containing the previous executable and receipt.
Keep that backup until you have checked the new client. Settings, hosts, aliases, and unrelated shell files remain unchanged.

A caught publication failure or SIGTERM attempts to restore both previous files from verified backups.
If rollback cannot complete, or SIGKILL interrupts replacement, preserve `.tailmux-transaction`, its named stage and backup, and `.tailmux-install-lock/owner`.
The error identifies a recognized pending transaction by ID. Ordinary install, replacement, and uninstall refuse it.
Do not delete a lock, rewrite a receipt, or publish files by hand to bypass that refusal.
Malformed records, mismatched digests, symlinks, and special files require owner inspection.

An interruption after transaction removal can leave a completed owned client and its owner lock without a transaction record.
Preserve the lock, stage, and backups for owner inspection. Transaction maintenance cannot validate a missing record.

## Resume or roll back a recognized pending transaction

Use the v0.3.0 verified README command and replace `install` on its last line with the arguments below.
For an independently reviewed offline checkout, prepend `bash setup.sh` to each argument line instead.
First preserve the transaction, stage, backup, and lock, then read the preview:

```text
recover --prefix "$HOME/.local/bin" --dry-run
```

Copy the exact recognized transaction ID and observed current executable SHA256.
These values refer to the current public executable, which may already be the candidate after an interrupted rename.
If the lifecycle lock remains, confirm that no writer is active before releasing it explicitly:

```text
recover --prefix "$HOME/.local/bin" --unlock-abandoned --transaction ID --expect-current-sha256 LOWER64HEX
```

`--unlock-abandoned` is your assertion that no lifecycle writer remains active.
It rechecks the recognized transaction, owner record, prefix, public pair, and verified stage and backup contents before releasing only that matching lock.
It does not resume or replace anything. There is no automatic age or PID unlock.
Unknown, malformed, recordless, and completed-cleanup locks require owner inspection.

After unlocking, choose one operation with the current digest and the same transaction ID:

```text
recover --prefix "$HOME/.local/bin" --resume --transaction ID --expect-current-sha256 LOWER64HEX
recover --prefix "$HOME/.local/bin" --rollback --transaction ID --expect-current-sha256 LOWER64HEX
```

Both operations acquire the ordinary lock and recheck the record and artifacts.
Resume requires the staged candidate to match the authenticated package or reviewed local candidate.
If candidates differ, use the matching authenticated release or reviewed checkout, or explicitly roll back.
A refused resume guard does not trigger implicit rollback.
Rollback restores the verified previous local content and receipt. It does not authenticate that history or change saved configuration.
Wrong IDs, changed current digests, third-party public bytes, or mismatched artifacts cause refusal and preserve the evidence.
Use a new preview after an interrupted maintenance operation because the current digest may have changed.
