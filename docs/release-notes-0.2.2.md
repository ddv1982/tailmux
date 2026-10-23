Tailmux 0.2.2 adds optional Sentry error reporting for local CLI failures.

- Enable reporting with your project's `TAILMUX_SENTRY_DSN`; it remains off by default.
- Capture dependency, daemon, status-validation, and local I/O failures with a source location, release, and environment.
- Exclude device names, addresses, usernames, command arguments, aliases, status snapshots, and diagnostic text from event payloads.
- Bound each HTTPS report to three seconds and preserve the original error status and SSH signal behavior.
- Include usage and monitoring configuration in the portable package.

Tailscale SSH and remote tmux failures are not captured. Live SSH and terminal acceptance remain NOT VERIFIED; offline Linux and macOS CI do not establish live compatibility.
