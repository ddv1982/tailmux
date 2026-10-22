#!/usr/bin/env bash

test_syntax_checks() {
  local sh_file
  local -a sh_files
  local shellcheck_out

  bash -n "$SETUP_SCRIPT" || fail "bash -n failed for setup.sh"
  while IFS= read -r sh_file; do
    sh_files+=("$sh_file")
    bash -n "$sh_file" || fail "bash -n failed for $sh_file"
  done < <(find "$REPO_ROOT/scripts/lib" "$REPO_ROOT/scripts/tests" -name '*.sh' | sort)

  command -v shellcheck >/dev/null 2>&1 || fail "shellcheck is required for lint"
  if ! shellcheck_out="$(shellcheck -x "$SETUP_SCRIPT" "${sh_files[@]}" 2>&1)"; then
    printf '%s\n' "$shellcheck_out" >&2
    fail 'shellcheck failed'
  fi
  pass "syntax checks"
}

test_tailmux_rejects_option_target() {
  local tmp
  local fake_bin
  local hosts_file
  local ssh_calls
  local out
  local status

  IFS=$'\t' read -r tmp fake_bin < <(create_fake_env)
  hosts_file="$tmp/home/hosts"
  ssh_calls="$tmp/home/ssh.calls"
  run_setup_with_input install $'y\nn\n' "$tmp/home" "$fake_bin" Linux >/dev/null

  cat > "$hosts_file" <<'HOSTS'
evil -oProxyCommand=whoami
HOSTS

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" TAILMUX_HOSTS_FILE="$hosts_file" bash -c 'source "$HOME/.profile"; tailmux evil' 2>&1)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected unsafe target rejection"
  [[ "$out" == *"refusing unsafe destination"* ]] || fail "expected unsafe destination message"
  if [[ -f "$ssh_calls" ]] && [[ -s "$ssh_calls" ]]; then
    fail "ssh should not be invoked for unsafe destination"
  fi
  pass "tailmux rejects option-style targets"
}

test_tailmux_help_flag() {
  local tmp
  local fake_bin
  local ssh_calls
  local out
  IFS=$'\t' read -r tmp fake_bin < <(create_fake_env)
  ssh_calls="$tmp/home/ssh.calls"
  run_setup_with_input install $'y\nn\n' "$tmp/home" "$fake_bin" Linux >/dev/null

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux --help')"
  [[ "$out" == *"Usage:"* ]] || fail "expected Usage in tailmux --help output"
  [[ "$out" == *"doctor"* ]] || fail "expected doctor subcommand in tailmux --help output"
  [[ "$out" == *"--version"* ]] || fail "expected --version in tailmux --help output"
  if [[ -f "$ssh_calls" ]] && [[ -s "$ssh_calls" ]]; then
    fail "ssh should not be invoked for --help"
  fi

  local out_h
  out_h="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux -h')"
  [[ "$out_h" == "$out" ]] || fail "expected -h output to match --help output"
  pass "tailmux --help flag"
}

test_tailmux_version_flag() {
  local tmp
  local fake_bin
  local out
  IFS=$'\t' read -r tmp fake_bin < <(create_fake_env)

  run_setup_with_input install $'y\nn\n' "$tmp/home" "$fake_bin" Linux >/dev/null

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailmux --version')"
  [[ "$out" =~ [0-9]+\.[0-9]+\.[0-9]+ ]] || fail "expected semver in tailmux --version output"

  local out_v
  out_v="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailmux -V')"
  [[ "$out_v" == "$out" ]] || fail "expected -V output to match --version output"
  pass "tailmux --version flag"
}

test_tailmux_resolver_ip_passthrough() {
  local tmp
  local fake_bin
  local ssh_calls
  local out
  IFS=$'\t' read -r tmp fake_bin < <(create_fake_env)
  ssh_calls="$tmp/home/ssh.calls"
  run_setup_with_input install $'y\nn\n' "$tmp/home" "$fake_bin" Linux >/dev/null

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux 100.64.0.42' 2>&1)"
  [[ "$out" == *"100.64.0.42"* ]] || fail "expected IP in output"
  [[ "$out" == *"input-ip"* ]] || fail "expected input-ip resolution mode"
  assert_contains "$ssh_calls" '100\.64\.0\.42'
  pass "tailmux resolver IP passthrough"
}
