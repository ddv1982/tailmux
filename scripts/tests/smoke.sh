#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SETUP_SCRIPT="$REPO_ROOT/setup.sh"
export TAILMUX_SKIP_MACOS_FILE_SHARING_PREF=1

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

pass() {
  echo "[PASS] $*"
}

assert_contains() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  if ! grep -Eq -- "$pattern" "$file"; then
    fail "Expected pattern '$pattern' in $file"
  fi
}

assert_not_contains() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  if grep -Eq -- "$pattern" "$file"; then
    fail "Did not expect pattern '$pattern' in $file"
  fi
}

assert_count() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  local expected="${3:?missing expected count}"
  local actual
  actual="$(grep -Ec -- "$pattern" "$file" || true)"
  [[ "$actual" == "$expected" ]] || fail "Expected $expected matches for '$pattern' in $file, got $actual"
}

assert_occurrences() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  local expected="${3:?missing expected count}"
  local actual
  actual="$(grep -oE -- "$pattern" "$file" | wc -l | tr -d ' ')"
  [[ "$actual" == "$expected" ]] || fail "Expected $expected occurrences for '$pattern' in $file, got $actual"
}

make_fake_bin() {
  local bin_dir="${1:?missing bin dir}"

  cat > "$bin_dir/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${TAILSCALE_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$TAILSCALE_CALLS_FILE"
fi
if [[ "${1:-}" == "status" && "${2:-}" == "--json" ]]; then
  if [[ -n "${TAILSCALE_STATUS_FAIL_FILE:-}" && -f "$TAILSCALE_STATUS_FAIL_FILE" ]]; then
    exit 1
  fi
  printf '{"BackendState":"Running","Self":{"HostName":"test-host"},"MagicDNSSuffix":"example.ts.net."}\n'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  if [[ -n "${TAILSCALE_STATUS_FAIL_FILE:-}" && -f "$TAILSCALE_STATUS_FAIL_FILE" ]]; then
    exit 1
  fi
  operator=""
  for arg in "$@"; do
    case "$arg" in
      --operator=*)
        operator="${arg#--operator=}"
        ;;
    esac
  done
  if [[ -n "$operator" ]]; then
    if [[ -n "${TAILSCALE_FAKE_OPERATOR_FILE:-}" && -f "$TAILSCALE_FAKE_OPERATOR_FILE" ]]; then
      configured="$(cat "$TAILSCALE_FAKE_OPERATOR_FILE" 2>/dev/null || true)"
      [[ "$configured" == "$operator" ]] && exit 0
    fi
    exit 1
  fi
  exit 0
fi
if [[ "${1:-}" == "set" || "${1:-}" == "up" ]]; then
  for arg in "$@"; do
    case "$arg" in
      --operator=*)
        if [[ -n "${TAILSCALE_FAKE_OPERATOR_FILE:-}" ]]; then
          printf '%s\n' "${arg#--operator=}" > "$TAILSCALE_FAKE_OPERATOR_FILE"
        fi
        ;;
    esac
  done
  exit 0
fi
if [[ "${1:-}" == "drive" ]]; then
  exit 0
fi
exit 0
BIN

  cat > "$bin_dir/tmux" <<'BIN'
#!/usr/bin/env bash
exit 0
BIN

  cat > "$bin_dir/sudo" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SUDO_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SUDO_CALLS_FILE"
fi
if [[ $# -eq 0 ]]; then
  exit 0
fi
cmd="${1:-}"
shift || true
case "$cmd" in
  rm|/bin/rm|/usr/bin/rm)
    if [[ -n "${SUDO_RM_CALLS_FILE:-}" ]]; then
      printf '%s\n' "$cmd $*" >> "$SUDO_RM_CALLS_FILE"
    fi
    exit 0
    ;;
  env)
    env "$@"
    ;;
  *)
    "$cmd" "$@"
    ;;
esac
BIN

  cat > "$bin_dir/ssh" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SSH_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SSH_CALLS_FILE"
fi
exit "${SSH_EXIT_CODE:-0}"
BIN

  cat > "$bin_dir/systemctl" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SYSTEMCTL_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SYSTEMCTL_CALLS_FILE"
fi
if [[ "${1:-}" == "is-active" ]]; then
  if [[ -n "${SSH_ACTIVE_FILE:-}" ]]; then
    if [[ -f "$SSH_ACTIVE_FILE" ]]; then
      exit 0
    fi
    exit 3
  fi
  exit 0
fi
if [[ "${1:-}" == "enable" && "${2:-}" == "--now" && ( "${3:-}" == "ssh" || "${3:-}" == "sshd" ) ]]; then
  if [[ -n "${SSH_ENABLE_FAIL_FILE:-}" && -f "$SSH_ENABLE_FAIL_FILE" ]]; then
    exit 1
  fi
  if [[ -n "${SSH_ACTIVE_FILE:-}" ]]; then
    : > "$SSH_ACTIVE_FILE"
  fi
  exit 0
fi
if [[ "${1:-}" == "enable" && "${2:-}" == "--now" && "${3:-}" == "tailscaled" ]]; then
  if [[ -n "${SYSTEMCTL_FIX_STATUS_FILE:-}" ]]; then
    rm -f "$SYSTEMCTL_FIX_STATUS_FILE"
  fi
  exit 0
fi
exit 0
BIN

  cat > "$bin_dir/apt-get" <<'BIN'
#!/usr/bin/env bash
exit 0
BIN

  chmod +x "$bin_dir/tailscale" "$bin_dir/tmux" "$bin_dir/sudo" "$bin_dir/ssh" "$bin_dir/systemctl" "$bin_dir/apt-get"
}

make_fake_macos_bin() {
  local bin_dir="${1:?missing bin dir}"
  local brew_prefix="${2:?missing brew prefix}"
  make_fake_bin "$bin_dir"
  mkdir -p "$brew_prefix/bin" "$brew_prefix/Cellar"
  cp "$bin_dir/tailscale" "$brew_prefix/bin/tailscale"

  cat > "$bin_dir/brew" <<'BIN'
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
shift || true
case "$cmd" in
  --prefix)
    printf '%s\n' "${BREW_PREFIX:?missing BREW_PREFIX}"
    ;;
  --cellar)
    printf '%s\n' "${BREW_PREFIX:?missing BREW_PREFIX}/Cellar"
    ;;
  list)
    if [[ "${1:-}" == "--formula" && "${2:-}" == "tailscale" ]]; then
      exit 0
    fi
    if [[ "${1:-}" == "--cask" ]]; then
      exit 1
    fi
    exit 1
    ;;
  install|link|unlink|uninstall)
    exit 0
    ;;
  services)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
BIN

  cat > "$bin_dir/sudo" <<'BIN'
#!/usr/bin/env bash
"$@"
BIN

  chmod +x "$bin_dir/brew" "$bin_dir/sudo"
}

test_syntax_checks() {
  local sh_file
  local shellcheck_out
  local shellcheck_codes

  bash -n "$SETUP_SCRIPT" || fail "bash -n failed for setup.sh"
  while IFS= read -r sh_file; do
    bash -n "$sh_file" || fail "bash -n failed for $sh_file"
  done < <(find "$REPO_ROOT/scripts/lib" -name '*.sh' | sort)

  shellcheck_out="$(shellcheck "$SETUP_SCRIPT" "$REPO_ROOT"/scripts/lib/*.sh 2>&1 || true)"
  shellcheck_codes="$(printf '%s\n' "$shellcheck_out" | grep -oE 'SC[0-9]+' | sort -u | tr '\n' ' ' || true)"
  if [[ -n "$shellcheck_codes" && "$shellcheck_codes" != "SC2016 " ]]; then
    printf '%s\n' "$shellcheck_out" >&2
    fail "unexpected shellcheck findings: $shellcheck_codes"
  fi
  pass "syntax checks"
}

test_loader_missing_module_fails() {
  local tmp
  local out
  local status
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts/lib"

  cp "$SETUP_SCRIPT" "$tmp/setup.sh"
  cp "$REPO_ROOT/scripts/lib/constants.sh" "$tmp/scripts/lib/constants.sh"

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$tmp/setup.sh" install 2>&1)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected missing-module loader failure"
  [[ "$out" == *"Required module missing:"* ]] || fail "expected missing-module error message"
  pass "loader missing-module failure"
}

test_install_idempotent() {
  local tmp
  local fake_bin
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
y
n
INP
)"
  [[ "$out" == *"Setup complete!"* ]] || fail "expected setup completion"
  assert_contains "$tmp/home/.profile" '^# >>> tailmux managed block \(tailmux\) >>>$'

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
n
INP
)"
  [[ "$out" == *"Core setup is already installed!"* ]] || fail "expected idempotent core setup message"
  pass "install idempotence"
}

test_stale_tailmux_refresh() {
  local tmp
  local fake_bin
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$tmp/home/.profile" <<'RC'
# >>> tailmux managed block (tailmux) >>>
tailmux() { echo hi; }
# <<< tailmux managed block (tailmux) <<<
RC

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
n
INP
)"

  [[ "$out" == *"Refreshing incomplete tailmux function managed block"* ]] || fail "expected tailmux managed block refresh"
  assert_contains "$tmp/home/.profile" '_tailmux_resolve_target\(\)'
  assert_contains "$tmp/home/.profile" '_tailmux_doctor\(\)'
  pass "stale tailmux refresh"
}

test_stale_taildrive_refresh() {
  local tmp
  local fake_bin
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$tmp/home/.profile" <<'RC'
# >>> tailmux managed block (tailmux) >>>
tailmux() { echo hi; }
# <<< tailmux managed block (tailmux) <<<

# >>> tailmux managed block (taildrive) >>>
# taildrive - file sharing over Tailscale
tailshare() { echo share; }
# <<< tailmux managed block (taildrive) <<<
RC

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
INP

  assert_contains "$tmp/home/.profile" '^tailmount\(\)'
  assert_contains "$tmp/home/.profile" '^tailumount\(\)'
  assert_contains "$tmp/home/.profile" '^tailmount-ls\(\)'
  pass "stale taildrive refresh"
}

test_taildrive_legacy_get_os_name_refresh() {
  local tmp
  local fake_bin
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$tmp/home/.profile" <<'RC'
# >>> tailmux managed block (tailmux) >>>
tailmux() { :; }
# <<< tailmux managed block (tailmux) <<<

# >>> tailmux managed block (taildrive) >>>
# taildrive - file sharing over Tailscale
tailshare() { :; }
tailunshare() { :; }
tailshare-ls() { :; }
tailmount() { local os_name; os_name="$(get_os_name)"; :; }
tailumount() { local os_name; os_name="$(get_os_name)"; :; }
tailmount-ls() { :; }
# <<< tailmux managed block (taildrive) <<<
RC

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install)"

  [[ "$out" == *"Refreshing incomplete taildrive functions managed block"* ]] || fail "expected taildrive managed block refresh"
  assert_contains "$tmp/home/.profile" '_taildrive_get_os_name\(\)'
  assert_not_contains "$tmp/home/.profile" '\$\(get_os_name\)'
  pass "taildrive legacy get_os_name refresh"
}

test_uninstall_removes_blocks() {
  local tmp
  local fake_bin
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" uninstall <<'INP' >/dev/null
y
y
n
n
INP

  assert_not_contains "$tmp/home/.profile" 'tailmux managed block \(tailmux\)'
  assert_not_contains "$tmp/home/.profile" 'tailmux managed block \(taildrive\)'
  pass "uninstall managed blocks"
}

test_linux_operator_configured() {
  local tmp
  local fake_bin
  local calls_file
  local operator_file
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  calls_file="$tmp/home/tailscale.calls"
  operator_file="$tmp/home/tailscale.operator"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILSCALE_CALLS_FILE="$calls_file" TAILSCALE_FAKE_OPERATOR_FILE="$operator_file" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
y
n
INP
)"

  [[ "$out" == *"Configured Tailscale operator user 'tailuser'"* ]] || fail "expected tailscale operator configuration message"
  assert_occurrences "$calls_file" '^set --operator=tailuser$' 1

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILSCALE_CALLS_FILE="$calls_file" TAILSCALE_FAKE_OPERATOR_FILE="$operator_file" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
n
INP
)"
  [[ "$out" == *"Configured Tailscale operator user 'tailuser'"* ]] || fail "expected tailscale operator configuration message on rerun"
  assert_occurrences "$calls_file" '^set --operator=tailuser$' 2
  pass "linux tailscale operator setup"
}

test_linux_unauthenticated_skips_operator() {
  local tmp
  local fake_bin
  local calls_file
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  calls_file="$tmp/home/tailscale.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  # Override tailscale to simulate NeedsLogin state
  cat > "$fake_bin/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${TAILSCALE_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$TAILSCALE_CALLS_FILE"
fi
if [[ "${1:-}" == "status" && "${2:-}" == "--json" ]]; then
  printf '{"BackendState":"NeedsLogin","Self":{"HostName":"test-host"}}\n'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  exit 0
fi
if [[ "${1:-}" == "set" && "${2:-}" == "--ssh" ]]; then
  exit 1
fi
exit 0
BIN
  chmod +x "$fake_bin/tailscale"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILSCALE_CALLS_FILE="$calls_file" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
y
n
INP
)"

  [[ "$out" == *"Tailscale needs authentication first"* ]] || fail "expected unauthenticated warning"
  [[ "$out" == *"sudo tailscale up --ssh"* ]] || fail "expected sudo tailscale up --ssh hint"
  [[ "$out" != *"Configured Tailscale operator user"* ]] || fail "should not configure operator when unauthenticated"
  [[ "$out" != *"Tailscale SSH enabled"* ]] || fail "should not report Tailscale SSH enabled while unauthenticated"
  # Verify no operator set calls were made
  if grep -q '^set --operator=' "$calls_file" 2>/dev/null; then
    fail "should not attempt operator set when unauthenticated"
  fi
  pass "linux unauthenticated skips operator setup"
}

test_linux_starts_tailscaled_when_down() {
  local tmp
  local fake_bin
  local calls_file
  local status_fail_file
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  calls_file="$tmp/home/systemctl.calls"
  status_fail_file="$tmp/home/tailscale.down"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"
  : > "$status_fail_file"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser SYSTEMCTL_CALLS_FILE="$calls_file" SYSTEMCTL_FIX_STATUS_FILE="$status_fail_file" TAILSCALE_STATUS_FAIL_FILE="$status_fail_file" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
y
n
INP
)"

  [[ "$out" == *"Starting tailscaled service"* ]] || fail "expected tailscaled service start step"
  [[ "$out" == *"tailscaled service is running"* ]] || fail "expected tailscaled running confirmation"
  assert_occurrences "$calls_file" '^enable --now tailscaled$' 1
  pass "linux tailscaled auto-start"
}

test_linux_tailscale_ssh_enabled() {
  local tmp
  local fake_bin
  local calls_file
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  calls_file="$tmp/home/tailscale.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILSCALE_CALLS_FILE="$calls_file" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
y
n
INP
)"

  [[ "$out" == *"Enabling Tailscale SSH on this device"* ]] || fail "expected Tailscale SSH enable step"
  [[ "$out" == *"Tailscale SSH enabled"* ]] || fail "expected Tailscale SSH enabled message"
  assert_occurrences "$calls_file" '^set --ssh$' 1
  pass "linux tailscale ssh enabled"
}

test_malformed_tailmux_block_not_modified() {
  local tmp
  local fake_bin
  local out
  local status
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$tmp/home/.profile" <<'RC'
# >>> tailmux managed block (tailmux) >>>
# malformed marker without tailmux function body
RC

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' 2>&1
y
n
INP
)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected install to fail with malformed managed block"
  [[ "$out" == *"tailmux function managed block is malformed"* ]] || fail "expected malformed block warning"

  assert_count "$tmp/home/.profile" '^# >>> tailmux managed block \(tailmux\) >>>$' 1
  assert_count "$tmp/home/.profile" '^# <<< tailmux managed block \(tailmux\) <<<$' 0
  assert_not_contains "$tmp/home/.profile" '^tailmux\(\)'
  pass "malformed tailmux block rejection"
}

test_macos_path_selection_mocked() {
  local tmp
  local fake_bin
  local brew_prefix
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  brew_prefix="$tmp/homebrew"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_macos_bin "$fake_bin" "$brew_prefix"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" BREW_PREFIX="$brew_prefix" TAILMUX_OS_OVERRIDE=Darwin TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP'
y
n
INP
)"

  [[ "$out" == *"Tailscale already installed (Homebrew formula)"* ]] || fail "expected mocked macOS formula path"
  [[ "$out" == *"Setup complete!"* ]] || fail "expected mocked macOS setup completion"
  assert_contains "$tmp/home/.profile" '^# >>> tailmux managed block \(tailmux\) >>>$'
  pass "mocked macOS tailscale path selection"
}

test_curl_style_bootstrap() {
  local tmp
  local fake_bin
  local out
  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_RAW_BASE="file://$REPO_ROOT" bash <(cat "$SETUP_SCRIPT") install <<'INP'
y
n
INP
)"
  [[ "$out" == *"Setup complete!"* ]] || fail "expected curl-style setup completion"
  assert_contains "$tmp/home/.profile" '^# >>> tailmux managed block \(tailmux\) >>>$'
  pass "curl-style bootstrap"
}

test_tailmux_rejects_option_target() {
  local tmp
  local fake_bin
  local hosts_file
  local ssh_calls
  local out
  local status

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  hosts_file="$tmp/home/hosts"
  ssh_calls="$tmp/home/ssh.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  cat > "$hosts_file" <<'HOSTS'
evil -oProxyCommand=whoami
HOSTS

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" TAILMUX_HOSTS_FILE="$hosts_file" bash -lc 'source "$HOME/.profile"; tailmux evil' 2>&1)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected unsafe target rejection"
  [[ "$out" == *"refusing unsafe destination"* ]] || fail "expected unsafe destination message"
  if [[ -f "$ssh_calls" ]] && [[ -s "$ssh_calls" ]]; then
    fail "ssh should not be invoked for unsafe destination"
  fi
  pass "tailmux rejects option-style targets"
}

test_uninstall_tailscale_state_requires_typed_confirmation() {
  local tmp
  local fake_bin
  local rm_calls
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  rm_calls="$tmp/home/sudo-rm.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SUDO_RM_CALLS_FILE="$rm_calls" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" uninstall <<'INP'
n
n
n
y
WRONG_TOKEN
INP
)"

  [[ "$out" == *"Skipped deleting Tailscale state directories."* ]] || fail "expected skipped state deletion message"
  if [[ -f "$rm_calls" ]] && grep -q '/var/lib/tailscale\|/etc/tailscale' "$rm_calls"; then
    fail "unexpected tailscale state deletion when confirmation token is wrong"
  fi
  pass "uninstall state deletion requires typed confirmation"
}

test_uninstall_tailscale_state_deletes_with_typed_confirmation() {
  local tmp
  local fake_bin
  local rm_calls
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  rm_calls="$tmp/home/sudo-rm.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SUDO_RM_CALLS_FILE="$rm_calls" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" uninstall <<'INP'
n
n
n
y
DELETE_TAILSCALE_STATE
INP
)"

  [[ "$out" == *"Removing Tailscale state and configuration..."* ]] || fail "expected state deletion step when token matches"
  assert_contains "$rm_calls" '/var/lib/tailscale'
  assert_contains "$rm_calls" '/etc/tailscale'
  pass "uninstall state deletion with typed confirmation"
}

main() {
  test_syntax_checks
  test_loader_missing_module_fails
  test_install_idempotent
  test_stale_tailmux_refresh
  test_stale_taildrive_refresh
  test_taildrive_legacy_get_os_name_refresh
  test_uninstall_removes_blocks
  test_linux_operator_configured
  test_linux_unauthenticated_skips_operator
  test_linux_starts_tailscaled_when_down
  test_linux_tailscale_ssh_enabled
  test_malformed_tailmux_block_not_modified
  test_macos_path_selection_mocked
  test_curl_style_bootstrap
  test_tailmux_rejects_option_target
  test_uninstall_tailscale_state_requires_typed_confirmation
  test_uninstall_tailscale_state_deletes_with_typed_confirmation
  echo "All smoke tests passed."
}

main "$@"
