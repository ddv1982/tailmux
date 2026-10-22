# shellcheck shell=bash
do_uninstall() {
  local rc
  while IFS= read -r rc; do
    inspect_rc "$rc" > /dev/null || return 1
  done < <(rc_paths)
  while IFS= read -r rc; do
    core_rc_operation uninstall "$rc" || return 1
  done < <(rc_paths)
  printf '%s\n' 'Core uninstall complete. Open a fresh shell to discard loaded functions.' \
    'Legacy Taildrive blocks remain operator-owned. See docs/taildrive.md.'
}
