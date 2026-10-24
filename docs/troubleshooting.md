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

## Replace an unchanged owned client from a reviewed checkout

Use the local replacement option with the same absolute prefix as the existing installation:

```bash
/bin/bash setup.sh install --replace-owned --prefix "$HOME/.local/bin"
```

This option requires an existing regular executable whose bytes match its valid receipt.
It does not inspect or migrate RC files. Unknown legacy blocks or an unrelated ZDOTDIR do not block replacement.
Keep using ordinary `install` for a fresh prefix or receipt-only recovery.
The public installer and its `update` action have not changed to this local replacement path.

Successful replacement retains a private `.tailmux-backup.*` directory containing the previous executable and receipt.
Check the printed absolute executable path and retain that backup until you have checked the new client.
The receipt proves local bookkeeping, not publisher authenticity. Review or authenticate the candidate separately.

If replacement fails, read the nonzero result and rollback message.
A caught publication failure or SIGTERM attempts to restore both previous files from verified backups.
If rollback cannot complete, or SIGKILL interrupts replacement, preserve `.tailmux-transaction`, its named stage and backup, and `.tailmux-install-lock/owner`.
The error identifies a recognized pending transaction by ID. Install, replacement, and uninstall refuse it without further changes.
Do not delete a lock, rewrite a receipt, or rerun publication by hand to bypass that refusal.
P1 has no operator resume, rollback, or abandoned-lock command. Have the owner inspect the saved record and artifacts before any manual recovery.
Malformed records, mismatched digests, symlinks, and special files require owner inspection and remain untouched.

An interruption after transaction removal can leave a completed owned client and its owner lock without a transaction record.
All lifecycle commands still refuse that lock. Preserve the lock, stage, and backups for owner inspection.
A recovery procedure that requires a recognized pending transaction does not apply when its record is absent.
