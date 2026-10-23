Tailmux 0.2.1 fixes upgrades from legacy Linux installations.

- Migrate recognized legacy shell blocks on Linux, preserving surrounding content, permissions, extended attributes, and verified backups.
- Accept security-context mode indicators while retaining ACL and metadata checks.
- Report setup failures directly without a Python traceback in the README command.
- Keep the verified shell entrypoint for install, update, and uninstall.
