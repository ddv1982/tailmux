#!/usr/bin/env bash

test_detect_shell_rc_precedence() {
  local tmp
  local out

  tmp="$(mktemp -d)"
  mkdir -p "$tmp/home"

  out="$(HOME="$tmp/home" SHELL=/bin/zsh bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; detect_shell_rc')"
  [[ "$out" == "$tmp/home/.zshrc" ]] || fail "expected zsh rc path"

  : > "$tmp/home/.bashrc"
  out="$(HOME="$tmp/home" SHELL=/bin/bash bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; detect_shell_rc')"
  [[ "$out" == "$tmp/home/.bashrc" ]] || fail "expected bashrc path"

  rm -f "$tmp/home/.bashrc"
  : > "$tmp/home/.bash_profile"
  out="$(HOME="$tmp/home" SHELL=/bin/bash bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; detect_shell_rc')"
  [[ "$out" == "$tmp/home/.bash_profile" ]] || fail "expected bash_profile path"

  rm -f "$tmp/home/.bash_profile"
  out="$(HOME="$tmp/home" SHELL=/bin/bash bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; detect_shell_rc')"
  [[ "$out" == "$tmp/home/.profile" ]] || fail "expected profile fallback path"

  pass "detect_shell_rc precedence"
}

test_remote_module_fetch_failure_reports_url() {
  local tmp
  local out
  local status

  tmp="$(mktemp -d)"
  mkdir -p "$tmp/home"

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash TAILMUX_RAW_BASE='file:///does-not-exist' bash "$SETUP_SCRIPT" install 2>&1)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected remote module fetch failure"
  [[ "$out" == *"Failed to download required module"* ]] || fail "expected download failure message"
  [[ "$out" == *"scripts/lib/constants.sh"* ]] || fail "expected module path in failure message"
  pass "remote module fetch failure includes module url"
}

test_linux_tailscaled_failure_is_fatal() {
  local tmp
  local fake_bin
  local down_file
  local out
  local status

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  down_file="$tmp/home/tailscale.down"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"
  : > "$down_file"

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILSCALE_STATUS_FAIL_FILE="$down_file" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' 2>&1
y
n
INP
)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected install failure when tailscaled stays down"
  [[ "$out" == *"tailscaled is not running; cannot continue Linux setup."* ]] || fail "expected tailscaled failure error"
  [[ "$out" == *"sudo systemctl status tailscaled --no-pager"* ]] || fail "expected systemctl debug hint"
  pass "linux tailscaled failure is fatal"
}

test_linux_authenticated_ssh_enable_failure_hints_manual_step() {
  local tmp
  local fake_bin
  local out
  local status

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "status" && "${2:-}" == "--json" ]]; then
  printf '{"BackendState":"Running","Self":{"HostName":"test-host"},"MagicDNSSuffix":"example.ts.net."}\n'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  exit 0
fi
if [[ "${1:-}" == "set" && "${2:-}" == "--ssh" ]]; then
  exit 1
fi
if [[ "${1:-}" == "set" && "${2:-}" == --operator=* ]]; then
  exit 0
fi
if [[ "${1:-}" == "up" ]]; then
  exit 0
fi
if [[ "${1:-}" == "drive" ]]; then
  exit 0
fi
exit 0
BIN
  chmod +x "$fake_bin/tailscale"

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' 2>&1
y
n
INP
)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected install to fail when SSH enable fails while authenticated"
  [[ "$out" == *"Could not enable Tailscale SSH automatically."* ]] || fail "expected SSH enable failure warning"
  [[ "$out" == *"Run manually: sudo tailscale set --ssh"* ]] || fail "expected manual SSH set hint"
  pass "authenticated SSH enable failure gives manual hint"
}

run_core_install_suite() {
  test_loader_missing_module_fails
  test_install_idempotent
  test_stale_tailmux_refresh
  test_stale_taildrive_refresh
  test_taildrive_legacy_get_os_name_refresh
  test_linux_operator_configured
  test_linux_unauthenticated_skips_operator
  test_linux_starts_tailscaled_when_down
  test_tailscale_ssh_enabled
  test_macos_tailscale_ssh_enabled
  test_linux_tailscale_policy_propagation
  test_linux_tailscale_policy_default_latest
  test_linux_tailscale_policy_reconciles_when_installed
  test_linux_preinstalled_tailscale_reconcile_failure_non_fatal
  test_curl_style_bootstrap
  test_setup_help_flag
  test_setup_version_flag
  test_setup_unknown_command_fails
  test_tailmux_help_flag
  test_tailmux_version_flag
  test_detect_shell_rc_precedence
  test_remote_module_fetch_failure_reports_url
  test_linux_tailscaled_failure_is_fatal
  test_linux_authenticated_ssh_enable_failure_hints_manual_step
}
