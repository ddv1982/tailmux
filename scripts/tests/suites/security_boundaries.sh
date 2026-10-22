#!/usr/bin/env bash

test_security_remote_command() (
  local tmp shell payload mode target out exit_code expected control_command
  local -a shells payloads
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  source "$REPO_ROOT/scripts/lib/constants.sh"
  printf '%s\n' "$TAILMUX_FUNC" > "$tmp/runtime.sh"
  cat > "$tmp/remote.sh" <<'DRIVER'
source "$SECURITY_RUNTIME"
ssh() {
  [[ $# -eq 4 && "$1" == -t && "$2" == -- && "$3" == "$SECURITY_TARGET" ]] || return 90
  printf '%s\n' "$4" > "$SECURITY_COMMAND"
  PATH=/remote/owned/bin:/usr/bin:/bin /bin/sh -c '
    tmux() {
      printf "%s\n" "$1" >> "$SECURITY_TRACE"
      printf "%s\n" "$PATH" > "$SECURITY_REMOTE_PATH"
      case "$SECURITY_MODE:$1" in
        attach:attach|new:new) return 0 ;;
        *) return 1 ;;
      esac
    }
    if [ "$SECURITY_MODE" = missing ]; then
      command() { return 1; }
    fi
    eval "$1"
  ' sh "$4"
}
PATH="$SECURITY_LOCAL_PATH"
tailmux "$SECURITY_TARGET"
result=$?
[[ "$PATH" == "$SECURITY_LOCAL_PATH" ]] || exit 91
exit "$result"
DRIVER
  shells=(/bin/bash)
  if command -v zsh >/dev/null 2>&1; then
    shells+=("$(command -v zsh)")
  fi
  payloads=(
    '/usr/bin:/bin'
    $'/usr/bin:/bin:$(printf injected > "$SECURITY_MARKER")'
    $'/usr/bin:/bin:`printf injected > "$SECURITY_MARKER"`'
    $'/usr/bin:/bin:"; printf injected > "$SECURITY_MARKER"; #'
    "/usr/bin:/bin:space dir/single'quote/double\"quote"
  )
  for shell in "${shells[@]}"; do
    control_command=""
    for payload in "${payloads[@]}"; do
      for mode in attach new missing; do
        for target in 100.64.0.2 fd7a:115c:a1e0::2; do
          : > "$tmp/trace"
          rm -f "$tmp/marker" "$tmp/remote-path"
          exit_code=0
          out="$(SECURITY_RUNTIME="$tmp/runtime.sh" SECURITY_TARGET="$target" \
            SECURITY_COMMAND="$tmp/command" SECURITY_TRACE="$tmp/trace" \
            SECURITY_REMOTE_PATH="$tmp/remote-path" SECURITY_MARKER="$tmp/marker" \
            SECURITY_LOCAL_PATH="$payload" SECURITY_MODE="$mode" \
            "$shell" "$tmp/remote.sh" 2>&1)" || exit_code=$?
          [[ ! -e "$tmp/marker" ]] || fail "local PATH executed remote shell syntax ($shell, $mode, marker=$(cat "$tmp/marker"))"
          if [[ "$mode" == missing ]]; then
            [[ $exit_code -eq 127 && "$out" == *'tmux not found on remote'* ]] || fail "missing remote tmux must return 127 ($shell): $out"
            [[ ! -s "$tmp/trace" ]] || fail "missing remote tmux must not start a session"
          else
            [[ $exit_code -eq 0 ]] || fail "remote $mode failed ($shell): $out"
            expected=attach
            [[ "$mode" != new ]] || expected=$'attach\nnew'
            [[ "$(cat "$tmp/trace")" == "$expected" ]] || fail "remote attach-any/new behavior changed ($shell)"
          fi
          if [[ -z "$control_command" ]]; then
            control_command="$(cat "$tmp/command")"
            pass "remote attach control ($shell)"
          fi
          [[ "$(cat "$tmp/command")" == "$control_command" ]] || fail "remote command depends on local PATH or destination"
          if [[ "$mode" != missing && "$payload" != /usr/bin:/bin ]]; then
            [[ "$(cat "$tmp/remote-path")" == /remote/owned/bin:/usr/bin:/bin ]] || fail "remote-owned PATH was replaced ($shell)"
          fi
        done
      done
    done
  done
  pass "fixed remote command, hostile PATH corpus, IPv6, attach-any, new, and missing tmux"
)

# shellcheck disable=SC2329
security_mount_fixture() {
  security_calls_file="$1"
  source "$REPO_ROOT/scripts/lib/taildrive_templates.sh"
  eval "$TAILDRIVE_SHARE_FUNCS"
  eval "$TAILDRIVE_MOUNT_FUNCS"
  security_record() {
    printf '<%s>' "$@" >> "$security_calls_file"
    printf '\n' >> "$security_calls_file"
  }
  _taildrive_magicdns_suffix() { security_record suffix; printf '%s\n' example.ts.net.; }
  uname() { security_record uname "$@"; printf '%s\n' "$os"; }
  mkdir() { security_record mkdir "$@"; }
  mount.davfs() { return 0; }
  mount() { security_record mount "$@"; return "$mount_exit_code"; }
  mount_webdav() { security_record mount_webdav "$@"; return 0; }
  umount() { security_record umount "$@"; return "$umount_exit_code"; }
  fusermount() { security_record fusermount "$@"; return "$fuse_exit_code"; }
  diskutil() { security_record diskutil "$@"; return 0; }
  sudo() { security_record sudo "$@"; return "$sudo_exit_code"; }
}

test_security_mount_rejection() (
  local tmp os operation operand out exit_code
  local mount_exit_code=1 umount_exit_code=1 fuse_exit_code=1 sudo_exit_code=1
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  security_mount_fixture "$tmp/calls"
  for os in Linux Darwin; do
    for operation in tailumount tailmount; do
      for operand in -a --all relative ./relative ../relative 'fd7a:115c:a1e0::2' ''; do
        : > "$tmp/calls"
        exit_code=0
        out="$("$operation" host docs "$operand" 2>&1)" || exit_code=$?
        [[ ! -s "$tmp/calls" ]] || fail "$operation accepted unsafe operand '$operand' ($os), utility trace=$(cat "$tmp/calls")"
        [[ $exit_code -eq 1 && "$out" == *'mount point must be an absolute path'* ]] || fail "$operation must reject '$operand' with an absolute-path error ($os): $out"
      done
      : > "$tmp/calls"
      exit_code=0
      out="$(HOME=relative "$operation" host docs 2>&1)" || exit_code=$?
      [[ ! -s "$tmp/calls" && $exit_code -eq 1 && "$out" == *'mount point must be an absolute path'* ]] || fail "$operation must validate the default mount point before utilities"
    done
  done
  pass "mount and unmount reject options, relative, IPv6-shaped, and empty operands before utilities"
)

test_security_mount_controls() (
  local tmp os operand out expected
  local mount_exit_code=0 umount_exit_code=0 fuse_exit_code=0 sudo_exit_code=0
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  security_mount_fixture "$tmp/calls"
  for os in Linux Darwin; do
    for operand in "$tmp/normal" "$tmp/space dir/\"quote\"/'single'/\`backtick\`/\$(literal)" "$tmp/fd7a:115c:a1e0::2"; do
      : > "$tmp/calls"
      out="$(tailmount host docs "$operand")" || fail "absolute mount control failed ($os)"
      [[ "$out" == "Mounted at $operand" ]] || fail "absolute mount did not report its operand"
      expected="<suffix>"$'\n'"<mkdir><-p><--><$operand>"$'\n'"<uname><-s>"$'\n'
      if [[ "$os" == Linux ]]; then
        expected+="<mount><-t><davfs><--><http://100.100.100.100:8080/example.ts.net/host/docs><$operand>"
      else
        expected+="<mount_webdav><http://100.100.100.100:8080/example.ts.net/host/docs><$operand>"
      fi
      [[ "$(cat "$tmp/calls")" == "$expected" ]] || fail "mount operand boundaries changed ($os): $(cat "$tmp/calls")"
      : > "$tmp/calls"
      out="$(tailumount host docs "$operand")" || fail "absolute unmount control failed ($os)"
      [[ "$out" == "Unmounted $operand" ]] || fail "absolute unmount did not report its operand"
      expected="<uname><-s>"$'\n'"<umount>"
      [[ "$os" != Linux ]] || expected+="<-->"
      expected+="<$operand>"
      [[ "$(cat "$tmp/calls")" == "$expected" ]] || fail "unmount operand boundaries changed ($os): $(cat "$tmp/calls")"
    done
  done
  pass "absolute mount and unmount controls preserve spaces, quotes, backticks, and IPv6 text"
)

test_security_mount_fallbacks() (
  local tmp os operand out expected
  local mount_exit_code=1 umount_exit_code=1 fuse_exit_code=1 sudo_exit_code=1
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  security_mount_fixture "$tmp/calls"
  operand="$tmp/space dir"
  os=Linux
  : > "$tmp/calls"
  out="$(tailumount host docs "$operand" 2>&1)" && fail "failed unmounts must return failure"
  [[ "$out" == *"Failed to unmount '$operand'"* ]] || fail "expected failed-unmount diagnostic"
  expected="<uname><-s>"$'\n'"<umount><--><$operand>"$'\n'"<fusermount><-u><--><$operand>"$'\n'"<sudo><umount><--><$operand>"$'\n'"<sudo><fusermount><-u><--><$operand>"
  [[ "$(cat "$tmp/calls")" == "$expected" ]] || fail "Linux unmount retry boundaries changed: $(cat "$tmp/calls")"
  fuse_exit_code=0
  : > "$tmp/calls"
  out="$(tailumount host docs "$operand")" || fail "fusermount control failed"
  [[ "$out" == "Unmounted $operand" ]] || fail "fusermount control did not report success"
  expected="<uname><-s>"$'\n'"<umount><--><$operand>"$'\n'"<fusermount><-u><--><$operand>"
  [[ "$(cat "$tmp/calls")" == "$expected" ]] || fail "fusermount success must stop retries"
  sudo_exit_code=0
  : > "$tmp/calls"
  out="$(tailmount host docs "$operand")" || fail "sudo mount control failed"
  [[ "$out" == *"Mounted at $operand"* ]] || fail "sudo mount control did not report success"
  expected="<suffix>"$'\n'"<mkdir><-p><--><$operand>"$'\n'"<uname><-s>"$'\n'"<mount><-t><davfs><--><http://100.100.100.100:8080/example.ts.net/host/docs><$operand>"$'\n'"<sudo><mount><-t><davfs><--><http://100.100.100.100:8080/example.ts.net/host/docs><$operand>"
  [[ "$(cat "$tmp/calls")" == "$expected" ]] || fail "Linux mount retry boundaries changed: $(cat "$tmp/calls")"
  os=Darwin
  : > "$tmp/calls"
  out="$(tailumount host docs "$operand")" || fail "diskutil control failed"
  [[ "$out" == "Unmounted $operand" ]] || fail "diskutil control did not report success"
  expected="<uname><-s>"$'\n'"<umount><$operand>"$'\n'"<diskutil><unmount><$operand>"
  [[ "$(cat "$tmp/calls")" == "$expected" ]] || fail "Darwin unmount fallback boundaries changed"
  pass "mount and unmount fallback argv, failure, and success controls"
)

test_security_taildrive_policy_example() {
  local actual expected
  actual="$(sed -n $'/^```jsonc\\{0,1\\}$/,/^```$/p' "$REPO_ROOT/docs/taildrive.md" | sed '/^```/d' | tr -d '[:space:]')"
  expected='{"nodeAttrs":[{"target":["group:devs"],"attr":["drive:access"]},{"target":["tag:fileserver"],"attr":["drive:share"]}]}{"grants":[{"src":["group:devs"],"dst":["tag:fileserver"],"app":{"tailscale.com/cap/drive":[{"shares":["myproject"],"access":"ro"}]}}]}'
  [[ "$actual" == "$expected" ]] || fail "Taildrive policy example must contain only scoped node attributes and a named-share read-only application grant; no network grants"
  pass "Taildrive policy example grants read-only myproject access without wildcard network grants"
}

run_security_boundaries_suite() {
  test_security_remote_command
  test_security_mount_rejection
  test_security_mount_controls
  test_security_mount_fallbacks
  test_security_taildrive_policy_example
}
