#!/usr/bin/env bash

test_uninstall_malformed_tailmux_block_warns_and_preserves_file() {
  local tmp
  local fake_bin
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$tmp/home/.profile" <<'RC'
# >>> tailmux managed block (tailmux) >>>
# malformed block without end marker
RC

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" uninstall <<'INP' 2>&1
y
n
n
n
INP
)"

  [[ "$out" == *"Tailmux managed block markers are malformed"* ]] || fail "expected malformed marker warning during uninstall"
  assert_count "$tmp/home/.profile" '^# >>> tailmux managed block \(tailmux\) >>>$' 1
  assert_count "$tmp/home/.profile" '^# <<< tailmux managed block \(tailmux\) <<<$' 0
  pass "uninstall malformed tailmux block warning"
}

test_uninstall_taildrive_prompts_davfs2_removal_on_linux() {
  local tmp
  local fake_bin
  local apt_calls

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  apt_calls="$tmp/home/apt.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/mount.davfs" <<'BIN'
#!/usr/bin/env bash
exit 0
BIN
  cat > "$fake_bin/apt-get" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${APT_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$APT_CALLS_FILE"
fi
exit 0
BIN
  chmod +x "$fake_bin/mount.davfs" "$fake_bin/apt-get"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" APT_CALLS_FILE="$apt_calls" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" uninstall <<'INP' >/dev/null
n
y
y
n
n
INP

  assert_contains "$apt_calls" '^remove -y davfs2$'
  pass "uninstall taildrive prompts davfs2 removal"
}

run_extended_uninstall_edges_suite() {
  test_uninstall_removes_blocks
  test_uninstall_tailscale_state_requires_typed_confirmation
  test_uninstall_tailscale_state_deletes_with_typed_confirmation
  test_malformed_tailmux_block_not_modified
  test_uninstall_malformed_tailmux_block_warns_and_preserves_file
  test_uninstall_taildrive_prompts_davfs2_removal_on_linux
}
