# Migrate legacy Taildrive helpers

Taildrive shell helpers are removed from this client.
Core installation does not create shares, mount or unmount filesystems, install mount helpers, or change network policy.
Manage any existing shares and mounts through their own operator-owned tools.
Uninstalling Tailmux does not unmount filesystems or delete shared data.

On macOS, install or uninstall from this reviewed local checkout to remove exact recognized legacy Taildrive managed blocks:

```bash
bash setup.sh install
bash setup.sh uninstall
```

Automatic migration recognizes the original and containment-patched managed bodies on macOS and Linux.
Linux migration needs GNU cp, lsattr, and Python 3; unsupported metadata still needs removal through your dotfiles owner.
Use v0.2.1 or later for automatic Linux migration; v0.2.0 requires manual block removal on Linux.
Setup refuses managed markers before lifecycle writes and makes no Linux RC metadata-preservation claim.
It saves a protected byte-for-byte RC backup and preserves unrelated shell code.
Unknown or changed bodies, malformed markers, and symlinked RC writes require manual inspection through your dotfiles owner.
Existing shells can retain loaded `tailshare`, `tailmount`, or `tailumount` functions until restarted.
The installer does not evaluate shell configuration or claim to discover every function.

Taildrive is outside this development client's release scope.
Any reintroduction needs separate ownership, mount identity, path encoding, least-privilege policy, and platform tests.
