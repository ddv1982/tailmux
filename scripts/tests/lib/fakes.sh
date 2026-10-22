#!/usr/bin/env bash

create_fake_env() {
  local tmp fake_bin
  tmp="$(mktemp -d)"
  tmp="$(cd -P "$tmp" && pwd)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"
  printf '%s\t%s\n' "$tmp" "$fake_bin"
}

run_setup_with_input() {
  local command="$1" input="$2" home_dir="$3" fake_bin="$4"
  shift 5
  printf '%s' "$input" | env HOME="$home_dir" ZDOTDIR="$home_dir" SHELL=/bin/bash \
    PATH="$fake_bin:$PATH" "$@" bash "$SETUP_SCRIPT" "$command"
}

make_fake_bin() {
  local bin_dir="$1" name
  for name in sudo curl wget brew apt apt-get dnf yum pacman systemctl launchctl mount umount fusermount; do
    cat > "$bin_dir/$name" <<'BIN'
#!/usr/bin/env bash
printf 'Forbidden command: %s %s\n' "${0##*/}" "$*" >&2
exit 97
BIN
    chmod +x "$bin_dir/$name"
  done
  cat > "$bin_dir/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${TAILSCALE_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$TAILSCALE_CALLS_FILE"
fi
case "$*" in
  'status --json') printf '%s\n' '{"BackendState":"Running","Self":{"HostName":"test-host"},"MagicDNSSuffix":"example.ts.net."}' ;;
  status) exit 0 ;;
  'dns query '*) exit 1 ;;
  'debug prefs') printf '%s\n' '{"CorpDNS":true}' ;;
  'drive '* ) exit 0 ;;
  *) printf 'Forbidden Tailscale mutation: %s\n' "$*" >&2; exit 97 ;;
esac
BIN
  cat > "$bin_dir/ssh" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SSH_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SSH_CALLS_FILE"
fi
exit "${SSH_EXIT_CODE:-0}"
BIN
  chmod +x "$bin_dir/tailscale" "$bin_dir/ssh"
}

install_legacy_taildrive_fixture() {
  local home_dir="$1"
  source "$REPO_ROOT/scripts/lib/taildrive_templates.sh"
  printf '%s\n%s\n' "$TAILDRIVE_SHARE_FUNCS" "$TAILDRIVE_MOUNT_FUNCS" > "$home_dir/.profile"
}
