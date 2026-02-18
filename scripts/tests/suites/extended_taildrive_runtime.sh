#!/usr/bin/env bash

test_tailshare_missing_path_fails() {
  local tmp
  local fake_bin
  local out
  local status

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailshare docs /path/does-not-exist' 2>&1)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected tailshare to fail for missing path"
  [[ "$out" == *"does not exist"* ]] || fail "expected missing path error"
  pass "tailshare missing path fails"
}

test_tailshare_success_prints_mount_hint() {
  local tmp
  local fake_bin
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailshare docs "$HOME"')"
  [[ "$out" == *"Shared 'docs'"* ]] || fail "expected successful share message"
  [[ "$out" == *"tailmount test-host docs"* ]] || fail "expected mount hint with self hostname"
  pass "tailshare success prints mount hint"
}

test_tailmount_missing_magicdns_suffix_fails() {
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
  printf '%s\n' '{"BackendState":"Running","Self":{"HostName":"test-host"}}'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  exit 0
fi
if [[ "${1:-}" == "set" || "${1:-}" == "up" || "${1:-}" == "drive" ]]; then
  exit 0
fi
exit 0
BIN
  chmod +x "$fake_bin/tailscale"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  set +e
  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailmount linux-laptop docs' 2>&1)"
  status=$?
  set -e

  [[ $status -ne 0 ]] || fail "expected tailmount failure without MagicDNS suffix"
  [[ "$out" == *"Could not determine tailnet name"* ]] || fail "expected tailnet suffix error"
  pass "tailmount missing magicdns suffix fails"
}

test_tailmount_linux_retries_with_sudo() {
  local tmp
  local fake_bin
  local out
  local mount_point

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mount_point="$tmp/home/mnt"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/uname" <<'BIN'
#!/usr/bin/env bash
printf '%s\n' 'Linux'
BIN
  cat > "$fake_bin/mount.davfs" <<'BIN'
#!/usr/bin/env bash
exit 0
BIN
  cat > "$fake_bin/mount" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${TAILDRIVE_SUDO_MOUNT:-}" ]]; then
  exit 0
fi
exit 1
BIN
  cat > "$fake_bin/sudo" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "mount" ]]; then
  TAILDRIVE_SUDO_MOUNT=1 "$@"
  exit $?
fi
"$@"
BIN
  chmod +x "$fake_bin/uname" "$fake_bin/mount.davfs" "$fake_bin/mount" "$fake_bin/sudo"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailmount linux-laptop docs "'"$mount_point"'"' 2>&1)"
  [[ "$out" == *"retrying with sudo"* ]] || fail "expected sudo retry message"
  [[ "$out" == *"Mounted at"* ]] || fail "expected mount success output"
  pass "tailmount Linux retries with sudo"
}

test_tailumount_linux_falls_back_to_fusermount() {
  local tmp
  local fake_bin
  local out
  local mount_point

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mount_point="$tmp/home/mnt"
  mkdir -p "$fake_bin" "$tmp/home" "$mount_point"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/uname" <<'BIN'
#!/usr/bin/env bash
printf '%s\n' 'Linux'
BIN
  cat > "$fake_bin/umount" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN
  cat > "$fake_bin/fusermount" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "-u" ]]; then
  exit 0
fi
exit 1
BIN
  chmod +x "$fake_bin/uname" "$fake_bin/umount" "$fake_bin/fusermount"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailumount linux-laptop docs "'"$mount_point"'"' 2>&1)"
  [[ "$out" == *"Unmounted"* ]] || fail "expected unmount success output"
  pass "tailumount Linux falls back to fusermount"
}

run_extended_taildrive_runtime_suite() {
  test_tailshare_missing_path_fails
  test_tailshare_success_prints_mount_hint
  test_tailmount_missing_magicdns_suffix_fails
  test_tailmount_linux_retries_with_sudo
  test_tailumount_linux_falls_back_to_fusermount
}
