#!/usr/bin/env bash

test_update_reports_failure_when_upgrade_fails() {
  local tmp
  local fake_bin
  local brew_prefix
  local out
  local status

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  brew_prefix="$tmp/homebrew"
  mkdir -p "$fake_bin" "$tmp/home" "$brew_prefix/bin" "$brew_prefix/Cellar"
  make_fake_macos_bin "$fake_bin" "$brew_prefix"
  make_update_brew_fake "$fake_bin"

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" BREW_PREFIX="$brew_prefix" BREW_TAILSCALE_OUTDATED=1 BREW_FAIL_UPGRADE=1 TAILMUX_OS_OVERRIDE=Darwin TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" update <<'INP' 2>&1
y
INP
)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected update command to fail when upgrade fails"
  [[ "$out" == *"Failed to upgrade tailscale"* ]] || fail "expected per-package upgrade failure message"
  [[ "$out" == *"1 package(s) failed to upgrade"* ]] || fail "expected summary failure count"
  pass "update returns non-zero when package upgrade fails"
}

test_check_linux_pm_outdated_dnf_parsing() {
  local tmp
  local fake_bin
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin"

  cat > "$fake_bin/dnf" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "check-update" ]]; then
  printf '%s\n' 'tmux.x86_64 3.4-1 updates'
  exit 100
fi
exit 0
BIN
  chmod +x "$fake_bin/dnf"

  out="$(PATH="$fake_bin:/usr/bin:/bin" bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; source "'"$REPO_ROOT"'/scripts/lib/package_manager.sh"; source "'"$REPO_ROOT"'/scripts/lib/update.sh"; detect_linux_package_manager(){ echo dnf; }; set +e; v="$(_check_linux_pm_outdated tmux)"; s=$?; set -e; printf "status=%s\nvalue=%s\n" "$s" "$v"')"
  [[ "$out" == *"status=0"* ]] || fail "expected dnf branch to report outdated"
  [[ "$out" == *"value=3.4-1"* ]] || fail "expected parsed dnf version"
  pass "dnf outdated parser"
}

test_check_linux_pm_outdated_yum_parsing() {
  local tmp
  local fake_bin
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin"

  cat > "$fake_bin/yum" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "check-update" ]]; then
  printf '%s\n' 'tmux.x86_64 3.5-2 updates'
  exit 100
fi
exit 0
BIN
  chmod +x "$fake_bin/yum"

  out="$(PATH="$fake_bin:/usr/bin:/bin" bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; source "'"$REPO_ROOT"'/scripts/lib/package_manager.sh"; source "'"$REPO_ROOT"'/scripts/lib/update.sh"; detect_linux_package_manager(){ echo yum; }; set +e; v="$(_check_linux_pm_outdated tmux)"; s=$?; set -e; printf "status=%s\nvalue=%s\n" "$s" "$v"')"
  [[ "$out" == *"status=0"* ]] || fail "expected yum branch to report outdated"
  [[ "$out" == *"value=3.5-2"* ]] || fail "expected parsed yum version"
  pass "yum outdated parser"
}

test_check_linux_pm_outdated_pacman_parsing() {
  local tmp
  local fake_bin
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin"

  cat > "$fake_bin/pacman" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "-Qu" ]]; then
  printf '%s\n' 'tmux 3.3a-1 -> 3.4-1'
  exit 0
fi
exit 0
BIN
  chmod +x "$fake_bin/pacman"

  out="$(PATH="$fake_bin:/usr/bin:/bin" bash -c 'source "'"$REPO_ROOT"'/scripts/lib/platform.sh"; source "'"$REPO_ROOT"'/scripts/lib/package_manager.sh"; source "'"$REPO_ROOT"'/scripts/lib/update.sh"; detect_linux_package_manager(){ echo pacman; }; set +e; v="$(_check_linux_pm_outdated tmux)"; s=$?; set -e; printf "status=%s\nvalue=%s\n" "$s" "$v"')"
  [[ "$out" == *"status=0"* ]] || fail "expected pacman branch to report outdated"
  [[ "$out" == *"value=3.4-1"* ]] || fail "expected parsed pacman version"
  pass "pacman outdated parser"
}

run_extended_update_branches_suite() {
  test_update_no_outdated
  test_update_outdated_upgraded
  test_update_declined
  test_update_reports_failure_when_upgrade_fails
  test_check_linux_pm_outdated_dnf_parsing
  test_check_linux_pm_outdated_yum_parsing
  test_check_linux_pm_outdated_pacman_parsing
}
