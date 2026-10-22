# Troubleshoot the client

Run the printed absolute executable path if an existing shell alias or function shadows `tailmux`.
Setup preserves unmanaged shell code and does not modify your current shell.

```bash
"$HOME/.local/bin/tailmux" --version
"$HOME/.local/bin/tailmux" doctor
"$HOME/.local/bin/tailmux" doctor work.example.ts.net
```

Doctor with a selector reports the selected identity and address without connecting.
It does not read complete preferences, print environment variables, renew keys, or change configuration.

| Failure | Action |
| --- | --- |
| `missing-dependency` | Install the named tool through its existing package owner. |
| `daemon-unavailable` | Inspect the local Tailscale daemon through its operator-owned tools. No fallback connection was started. |
| `logged-out` | Ask the machine owner to restore the intended identity. Tailmux never logs in or out for you. |
| `stopped/not-ready` | Resolve the daemon's readiness state before retrying. |
| `invalid-schema` | Use a reviewed compatible status schema. Do not replace jq with a text parser. |
| `invalid-aliases` | Use exactly two fields per entry and canonical full-name or advertised-address targets. |
| `unknown-selector` | Copy a canonical name or address from your known peer inventory. Shared peers need a full name or explicit canonical alias. |
| `ambiguous-selector` | Resolve the duplicate identity name or address in the coordination inventory. Tailmux never chooses the first record. |
| `missing-advertised-host-keys` | Have the destination owner verify Tailscale SSH enablement and policy. Ordinary sshd reachability does not establish wrapper readiness. |
| `peer-key-expired` | Have the destination owner renew its intended node identity. Tailmux does not renew it or infer expiry from dates. |

`Online:false` alone does not prevent a connection.
IPv6 accepts the advertised spelling, ignoring hexadecimal case.
Alternate compressed spellings are not normalized.
When the current tailnet suffix is unavailable or invalid, use a full canonical name or advertised address.

The App Store and TestFlight Tailscale variants do not expose `tailscale ssh`.
Tailmux propagates that wrapper error and does not replace the app or retry with ordinary SSH.
Wrapper errors, remote exit codes, and policy failures propagate through `exec`.
A remote account without tmux exits 127.
Configure tmux discovery in the remote account's PATH.

## Resolve lifecycle refusals

Setup accepts only absolute HOME, ZDOTDIR, and prefix paths without line breaks.
Spaces are supported.
It refuses unsafe writable ancestors, unexpected ACLs, unsupported metadata, ambiguous ownership, and symlinked writes.
The current user and root remain trusted owners.
These checks do not protect against a malicious process with the same UID or root privileges.

An unrelated symlinked RC can remain unchanged.
If a symlinked RC contains a legacy managed block, remove that exact block through your dotfiles owner and retry.
Unknown bodies or malformed markers require manual inspection.
Do not delete a block merely because its marker mentions Tailmux.

Automatic legacy RC migration is supported only on macOS.
On Linux, managed markers cause refusal before any lifecycle writes because this client cannot verify preservation of Linux inode flags and xattrs.
Remove the legacy block through your dotfiles owner, then retry install or uninstall.
Linux fresh installation and uninstall remain usable when no managed RC block needs changing.

A recognized macOS removal saves `.tailmux-backup.*/original` beside the RC before publication.
The backup directory is private and retains the original metadata.
Executable removal saves protected content-only backups under the selected prefix.
Those owned-client backups do not promise flag, xattr, or other metadata preservation.
Keep these backups until you have checked the migration.

Interrupted receipt-first publication can leave a receipt without an executable.
Retry the same reviewed source and prefix, or run uninstall to remove that owned receipt.
A pre-existing executable without a valid receipt remains foreign and requires manual inspection.
An interruption can also leave a lifecycle lock or stage directory.
After confirming no setup process is active, inspect those exact paths before removing the stale lock and retrying.
Setup never clears an unknown lock automatically.
A failed migration can leave the verified executable installed and some recognized blocks already removed.
The error remains nonzero. Retry after resolving the reported cause.
No lifecycle failure is reported as complete.
