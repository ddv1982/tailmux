# Troubleshoot setup and connections

## Resolve a setup refusal

Run `bash setup.sh --help` from a reviewed local checkout. Help and version need no modules, networking, or running Tailscale daemon.
Remote process-substitution setup is disabled. Setup never downloads replacement modules.
If a module is missing, restore the complete reviewed checkout before retrying.

An unknown or modified managed block is not proof of Tailmux ownership. Back up the RC and inspect its complete contents before changing it manually.
Resolve unmanaged `tailmux` functions or aliases yourself. Setup never overwrites them.
For symlinked dotfiles, remove or migrate the reviewed block through the tool that owns those files. Setup refuses symlinked RC files and ancestors.

RC files require current-user ownership, a single hard link, and no group or other write permission. Their direct parent requires current-user ownership and no group or other write permission.
Every ancestor must belong to the current user or root. Group or other writable ancestors require the sticky bit.
Setup refuses RC-file ACLs. On macOS, a directory can have the single default ACL entry `0: group:everyone deny delete`.
Setup preserves that deny-only directory ACL. It refuses all other directory ACL entries, including mutating grants on higher ancestors. Use operator-managed migration for refused cases.
Do not strip metadata to force installation. On macOS setup preserves and verifies xattrs, including automatic provenance. Unsupported metadata or failed preservation must remain a refusal.

A failed write returns an error and does not report completion. For an existing file, inspect its protected `.tailmux-backup.*/original` beside the RC before recovery.
Each RC replacement is atomic. An uninstall across multiple files can stop after an earlier file succeeds. Correct the failure and retry.
A `.tailmux-lock` directory indicates an active or interrupted operation. Confirm no setup process is running before manually removing a stale empty lock directory.
A crash can leave a private `.tailmux-stage.*` directory. Inspect it and its adjacent backup before manual cleanup.

Setup discovers standard Bash RC files and `${ZDOTDIR:-$HOME}/.zshrc`. Inspect custom sourced files separately.
Open a fresh shell after install or uninstall. A running shell can retain the old function.

## Restore client prerequisites

If Tailscale is missing, install it through your chosen package or application owner. Setup does not install dependencies or contact the daemon.
Keep the macOS variant you already use. Setup does not remove GUI apps or migrate them to Homebrew.
Use that application's or package owner's documented recovery process for daemon or authentication failures.
Do not delete networking state, log out, or replace packages as an automatic troubleshooting step.
`bash setup.sh update` is deprecated and runs no updater.

## Diagnose a legacy connection

Run `tailmux doctor <hostname>` to see the resolver's selected destination.
The legacy resolver can use system DNS and ordinary SSH. It does not enforce tailnet membership.
For short-name failures, try the tailnet FQDN or an explicit alias in `~/.config/tailmux/hosts`.
Keep SSH host-key checking enabled.

If access is denied or the connection is refused, ask the destination operator to check its SSH service, account authorization, and tailnet policy where applicable.
Enabling a destination server is a separate operator task. Installing this outbound client does not authorize changing the local device's inbound server settings.
If tmux is missing, ask the destination operator to install it and expose it in the remote account's noninteractive PATH.

## Handle legacy Taildrive

Core setup no longer provisions mounts, mount dependencies, or Taildrive helpers.
See [Taildrive legacy support and removal](taildrive.md) for the manual path.
