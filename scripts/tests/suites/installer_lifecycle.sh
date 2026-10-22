#!/usr/bin/env bash

lifecycle_fixture() {
  local tool target
  life_tmp="$(mktemp -d)"
  life_tmp="$(cd -P "$life_tmp" && pwd)"
  life_bin="$life_tmp/bin"
  mkdir "$life_bin" "$life_tmp/home"
  for tool in bash dirname uname stat ls tr cmp shasum sha256sum dd cat mkdir rmdir mktemp cp mv rm cut xattr wc; do
    target="$(command -v "$tool" || true)"
    [[ -z "$target" ]] || ln -s "$target" "$life_bin/$tool"
  done
  for tool in curl wget sudo su doas brew apt apt-get dnf yum pacman zypper apk port systemctl service launchctl defaults osascript open tailscale tailscaled ssh mount mount_webdav umount fusermount git; do
    cat > "$life_bin/$tool" <<'BIN'
#!/bin/bash
printf '%s %s\n' "${0##*/}" "$*" >> "$FORBIDDEN_TRACE"
exit 97
BIN
    chmod +x "$life_bin/$tool"
  done
  life_status=0
  life_out=''
}

lifecycle_run() {
  life_status=0
  life_out="$(env HOME="$life_tmp/home" ZDOTDIR="$life_tmp/home" SHELL=/bin/bash \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" \
    /bin/bash "${LIFE_SETUP:-$SETUP_SCRIPT}" "$@" 2>&1)" || life_status=$?
  [[ ! -s "$life_tmp/forbidden" ]] || fail "forbidden lifecycle process: $(cat "$life_tmp/forbidden")"
}

lifecycle_success() {
  [[ "$life_status" == 0 ]] || fail "lifecycle failed: $life_out"
}

lifecycle_refusal() {
  [[ "$life_status" != 0 && "$life_out" == *"$1"* ]] || fail "expected refusal '$1': $life_status $life_out"
  [[ "$life_out" != *'setup complete'* && "$life_out" != *'uninstall complete'* ]] || fail 'failed operation reported success'
}

test_lifecycle_offline_dispatch() (
  local life_tmp life_bin life_status=0 life_out='' LIFE_SETUP option
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  mkdir "$life_tmp/checkout"
  cp "$SETUP_SCRIPT" "$life_tmp/checkout/setup.sh"
  printf '%s\n' 'exit 99' > "$life_tmp/checkout/VERSION"
  LIFE_SETUP="$life_tmp/checkout/setup.sh"
  for option in --help -h --version -V; do
    lifecycle_run "$option"
    lifecycle_success
  done
  [[ "$life_out" == 'tailmux 0.1.0' ]] || fail 'unexpected offline version'
  lifecycle_run update
  lifecycle_refusal 'deprecated'
  lifecycle_run install
  lifecycle_refusal 'Required module missing:'
  lifecycle_run --help extra
  lifecycle_refusal 'Usage:'
  lifecycle_run unknown
  lifecycle_refusal 'Unknown command:'
  [[ -z "$(ls -A "$life_tmp/home")" ]] || fail 'offline commands touched HOME'
  pass 'help, version, update, and invalid commands run offline without modules or writes'
)

test_lifecycle_bootstrap_refusal() (
  local life_tmp life_bin life_status=0 life_out=''
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  cat > "$life_tmp/bootstrap.sh" <<'DRIVER'
bash <(cat "$SETUP_SCRIPT") install
DRIVER
  life_status=0
  life_out="$(env HOME="$life_tmp/home" PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" \
    SETUP_SCRIPT="$SETUP_SCRIPT" /bin/bash "$life_tmp/bootstrap.sh" 2>&1)" || life_status=$?
  lifecycle_refusal 'remote/process-substitution setup is disabled'
  [[ ! -s "$life_tmp/forbidden" && -z "$(ls -A "$life_tmp/home")" ]] || fail 'bootstrap attempted effects'
  pass 'process-substitution installer refuses without downloads or writes'
)

test_lifecycle_repeatability() (
  local life_tmp life_bin life_status=0 life_out='' expected mode
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  printf '%s\n' '# user settings' > "$life_tmp/home/.profile"
  chmod 640 "$life_tmp/home/.profile"
  cp "$life_tmp/home/.profile" "$life_tmp/before"
  lifecycle_run install
  lifecycle_success
  [[ "$life_out" == *'Core setup complete'* ]] || fail 'missing successful install message'
  assert_count "$life_tmp/home/.profile" '^# >>> tailmux managed block \(tailmux\) >>>$' 1
  assert_not_contains "$life_tmp/home/.profile" 'tailshare|tailmount'
  cmp -s "$life_tmp/before" "$life_tmp"/home/.tailmux-backup.*/original || fail 'backup content differs'
  mode="$(ls -l "$life_tmp/home/.profile")"
  [[ "$mode" == '-rw-r-----'* ]] || fail 'RC permissions changed'
  cp "$life_tmp/home/.profile" "$life_tmp/installed"
  lifecycle_run install
  lifecycle_success
  cmp -s "$life_tmp/home/.profile" "$life_tmp/installed" || fail 'repeat install changed RC'
  lifecycle_run uninstall
  lifecycle_success
  expected=$'# user settings\n\n'
  printf '%s' "$expected" > "$life_tmp/expected"
  cmp -s "$life_tmp/home/.profile" "$life_tmp/expected" || fail 'uninstall did not preserve outside bytes'
  lifecycle_run uninstall
  lifecycle_success
  cmp -s "$life_tmp/home/.profile" "$life_tmp/expected" || fail 'repeat uninstall changed RC'
  pass 'core install/uninstall repeat, preserve mode, backup, and outside bytes without dependency calls'
)

test_lifecycle_missing_tailscale() (
  local life_tmp life_bin life_status=0 life_out=''
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  rm "$life_bin/tailscale"
  lifecycle_run install
  lifecycle_success
  [[ "$life_out" == *'Tailscale is missing.'* ]] || fail 'missing prerequisite was not reported'
  lifecycle_run uninstall
  lifecycle_success
  pass 'missing Tailscale never triggers dependency installation'
)

test_lifecycle_ownership_refusals() (
  local life_tmp life_bin life_status=0 life_out='' body operation
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  for body in \
    'tailmux() { :; }' \
    'function tailmux { :; }' \
    'alias tailmux=other' \
    'alias -- tailmux=other' \
    "alias 'tailmux=other'" \
    'alias other=x tailmux=other' \
    'alias "tailmux=other"' \
    $'# >>> tailmux managed block (tailmux) >>>\nunknown\n# <<< tailmux managed block (tailmux) <<<' \
    $'# >>> tailmux managed block (tailmux) >>>\nunknown' \
    $'# <<< tailmux managed block (tailmux) <<<\n# >>> tailmux managed block (tailmux) >>>' \
    '# >>> tailmux managed block (unknown) >>>'; do
    printf '%s\n' "$body" > "$life_tmp/home/.profile"
    cp "$life_tmp/home/.profile" "$life_tmp/before"
    for operation in install uninstall; do
      lifecycle_run "$operation"
      [[ "$life_status" != 0 ]] || fail "accepted foreign RC: $body"
      cmp -s "$life_tmp/home/.profile" "$life_tmp/before" || fail 'refusal modified foreign RC'
      [[ -z "$(find "$life_tmp/home" -name '.tailmux-*' -print)" ]] || fail 'ownership refusal wrote staging or backup files'
    done
  done
  lifecycle_run install
  lifecycle_refusal 'Unknown or malformed managed marker'
  printf 'before\0after' > "$life_tmp/home/.profile"
  cp "$life_tmp/home/.profile" "$life_tmp/before"
  lifecycle_run install
  lifecycle_refusal 'RC contains NUL bytes'
  cmp -s "$life_tmp/before" "$life_tmp/home/.profile" || fail 'NUL input changed'
  pass 'foreign functions, alias, modified bodies, and malformed/unknown markers refuse before writes'
)

test_lifecycle_modified_and_multifile() (
  local life_tmp life_bin life_status=0 life_out=''
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  lifecycle_run install
  lifecycle_success
  printf '%s\n' 'tailmux() { :; }' > "$life_tmp/home/.bashrc"
  cp "$life_tmp/home/.profile" "$life_tmp/before"
  lifecycle_run uninstall
  lifecycle_refusal 'Unmanaged tailmux function'
  cmp -s "$life_tmp/home/.profile" "$life_tmp/before" || fail 'uninstall changed a file before full preflight'
  rm "$life_tmp/home/.bashrc"
  sed 's/tailmux() {/tailmux() { :;/' "$life_tmp/home/.profile" > "$life_tmp/modified"
  cp "$life_tmp/modified" "$life_tmp/home/.profile"
  lifecycle_run install
  lifecycle_refusal 'Unknown or modified core block'
  cmp -s "$life_tmp/modified" "$life_tmp/home/.profile" || fail 'modified core was overwritten'
  pass 'modified exact template and foreign second RC prevent changes'
)

test_lifecycle_symlink_and_permissions() (
  local life_tmp life_bin life_status=0 life_out='' operation bits
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  printf '%s\n' '# sentinel' > "$life_tmp/target"
  ln -s "$life_tmp/target" "$life_tmp/home/.profile"
  for operation in install uninstall; do
    lifecycle_run "$operation"
    lifecycle_refusal 'Symlinked RC paths and ancestors'
    [[ -L "$life_tmp/home/.profile" && "$(cat "$life_tmp/target")" == '# sentinel' ]] || fail 'RC symlink target changed'
  done
  rm "$life_tmp/home/.profile"
  mkdir "$life_tmp/actual"
  ln -s "$life_tmp/actual" "$life_tmp/home/link"
  life_status=0
  life_out="$(env HOME="$life_tmp/home/link" ZDOTDIR="$life_tmp/home/link" SHELL=/bin/bash \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" install 2>&1)" || life_status=$?
  lifecycle_refusal 'Symlinked RC paths and ancestors'
  [[ -z "$(ls -A "$life_tmp/actual")" ]] || fail 'symlinked ancestor was written'
  mkdir -p "$life_tmp/writable/nested"
  chmod 777 "$life_tmp/writable"
  life_status=0
  life_out="$(env HOME="$life_tmp/writable/nested" ZDOTDIR="$life_tmp/writable/nested" SHELL=/bin/bash \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" install 2>&1)" || life_status=$?
  lifecycle_refusal 'Group or other writable non-sticky RC ancestor is refused'
  [[ -z "$(ls -A "$life_tmp/writable/nested")" ]] || fail 'writable ancestor refusal created files'
  chmod 1777 "$life_tmp/writable"
  life_status=0
  life_out="$(env HOME="$life_tmp/writable/nested" ZDOTDIR="$life_tmp/writable/nested" SHELL=/bin/bash \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" install 2>&1)" || life_status=$?
  lifecycle_success
  for bits in 775 757; do
    chmod "$bits" "$life_tmp/home"
    lifecycle_run install
    lifecycle_refusal 'Group or other writable non-sticky RC ancestor is refused'
    [[ ! -e "$life_tmp/home/.profile" ]] || fail 'writable-parent refusal created RC'
  done
  chmod 755 "$life_tmp/home"
  printf '%s\n' '# sentinel' > "$life_tmp/home/.profile"
  for bits in 664 646; do
    chmod "$bits" "$life_tmp/home/.profile"
    lifecycle_run install
    lifecycle_refusal 'Group or other writable RC files are refused'
  done
  chmod 644 "$life_tmp/home/.profile"
  ln "$life_tmp/home/.profile" "$life_tmp/hardlink"
  lifecycle_run install
  lifecycle_refusal 'one hard link'
  [[ "$(cat "$life_tmp/hardlink")" == '# sentinel' ]] || fail 'hardlinked RC changed'
  pass 'symlinked RC and ancestors, writable parents/files, and hard links refuse'
)

test_lifecycle_write_failures() (
  local life_tmp life_bin life_status=0 life_out='' tool
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  printf '%s\n' '# sentinel' > "$life_tmp/home/.profile"
  cp "$life_tmp/home/.profile" "$life_tmp/before"
  for tool in mktemp cp cat mv; do
    rm "$life_bin/$tool"
    printf '#!/bin/bash\nexit 73\n' > "$life_bin/$tool"
    chmod +x "$life_bin/$tool"
    lifecycle_run install
    [[ "$life_status" != 0 && "$life_out" != *'setup complete'* ]] || fail "$tool failure reported success"
    cmp -s "$life_tmp/before" "$life_tmp/home/.profile" || fail "$tool failure changed original RC"
    rm "$life_bin/$tool"
    ln -s "$(command -v "$tool")" "$life_bin/$tool"
  done
  rm "$life_bin/mv"
  printf '#!/bin/bash\nexit 0\n' > "$life_bin/mv"
  chmod +x "$life_bin/mv"
  lifecycle_run install
  lifecycle_refusal 'Published RC content or metadata verification failed'
  cmp -s "$life_tmp/before" "$life_tmp/home/.profile" || fail 'false-success mv changed original'
  pass 'staging, copy, write, replacement, and false-success publication failures propagate'
)

test_lifecycle_zsh_and_legacy_taildrive() (
  local life_tmp life_bin life_status=0 life_out=''
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  mkdir "$life_tmp/home/zsh"
  source "$REPO_ROOT/scripts/lib/taildrive_templates.sh"
  printf '%s\n%s\n%s\n' '# >>> tailmux managed block (taildrive) >>>' \
    "$TAILDRIVE_SHARE_FUNCS" '# <<< tailmux managed block (taildrive) <<<' > "$life_tmp/home/zsh/.zshrc"
  cp "$life_tmp/home/zsh/.zshrc" "$life_tmp/before"
  life_out="$(env HOME="$life_tmp/home" ZDOTDIR="$life_tmp/home/zsh" SHELL=/bin/zsh \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" install 2>&1)" || life_status=$?
  lifecycle_success
  [[ ! -s "$life_tmp/forbidden" && ! -e "$life_tmp/home/.profile" ]] || fail 'Zsh install changed wrong path'
  env HOME="$life_tmp/home" ZDOTDIR="$life_tmp/home/zsh" SHELL=/bin/zsh \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" uninstall > "$life_tmp/out" 2>&1 || fail 'Zsh uninstall failed'
  printf '\n' >> "$life_tmp/before"
  cmp -s "$life_tmp/before" "$life_tmp/home/zsh/.zshrc" || fail 'legacy Taildrive bytes changed'
  pass 'configured ZDOTDIR lifecycle preserves legacy Taildrive block'
)

test_lifecycle_legacy_upgrade_and_byte_boundaries() (
  local life_tmp life_bin life_status=0 life_out='' rc
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  printf '# prefix café\n' > "$life_tmp/prefix"
  printf '# suffix without final newline Ω' > "$life_tmp/suffix"
  cat "$life_tmp/prefix" "$REPO_ROOT/scripts/tests/fixtures/legacy-core-0.1.0.rc" "$life_tmp/suffix" > "$life_tmp/home/.profile"
  lifecycle_run install
  lifecycle_success
  source "$REPO_ROOT/scripts/lib/constants.sh"
  { cat "$life_tmp/prefix"; printf '%s\n%s\n%s\n' "$TAILMUX_BLOCK_BEGIN" "$TAILMUX_FUNC" "$TAILMUX_BLOCK_END"; cat "$life_tmp/suffix"; } > "$life_tmp/expected"
  cmp -s "$life_tmp/expected" "$life_tmp/home/.profile" || fail 'recognized legacy upgrade changed outside bytes or failed to replace body'
  for rc in .bashrc .bash_profile .zshrc; do
    cp "$life_tmp/home/.profile" "$life_tmp/home/$rc"
  done
  lifecycle_run uninstall
  lifecycle_success
  cat "$life_tmp/prefix" "$life_tmp/suffix" > "$life_tmp/expected"
  for rc in .profile .bashrc .bash_profile .zshrc; do
    cmp -s "$life_tmp/expected" "$life_tmp/home/$rc" || fail "uninstall changed outside bytes in $rc"
  done
  cat "$REPO_ROOT/scripts/tests/fixtures/legacy-core-0.1.0.rc" "$REPO_ROOT/scripts/tests/fixtures/legacy-core-0.1.0.rc" > "$life_tmp/home/.profile"
  cp "$life_tmp/home/.profile" "$life_tmp/before"
  lifecycle_run install
  lifecycle_refusal 'Malformed core markers'
  cmp -s "$life_tmp/before" "$life_tmp/home/.profile" || fail 'duplicate blocks changed'
  pass 'recognized legacy upgrade, all standard RCs, duplicate blocks, Unicode, and missing final newline'
)

test_lifecycle_lock_and_readonly() (
  local life_tmp life_bin life_status=0 life_out=''
  lifecycle_fixture
  trap 'chmod u+w "$life_tmp/home/.profile"; rm -rf "$life_tmp"' EXIT
  printf '%s\n' '# sentinel' > "$life_tmp/home/.profile"
  mkdir "$life_tmp/home/.profile.tailmux-lock"
  lifecycle_run install
  lifecycle_refusal 'RC lifecycle is locked'
  rmdir "$life_tmp/home/.profile.tailmux-lock"
  chmod 444 "$life_tmp/home/.profile"
  lifecycle_run install
  lifecycle_refusal 'RC or parent is not writable'
  [[ "$(cat "$life_tmp/home/.profile")" == '# sentinel' ]] || fail 'readonly file changed'
  chmod 644 "$life_tmp/home/.profile"
  chmod 555 "$life_tmp/home"
  lifecycle_run install
  [[ "$life_status" != 0 && "$life_out" != *'setup complete'* ]] || fail 'readonly parent reported success'
  chmod 755 "$life_tmp/home"
  [[ -z "$(find "$life_tmp/home" -name '*.tailmux-lock' -o -name '.tailmux-stage.*')" ]] || fail 'failed run left staging/lock'
  pass 'existing lifecycle lock and real readonly file/parent refuse without false success'
)

test_lifecycle_macos_metadata() (
  local life_tmp life_bin life_status=0 life_out='' expected acl_before acl_home_before acl_after operation
  [[ "$(uname -s)" == Darwin ]] || return 0
  lifecycle_fixture
  trap '[[ ! -d "$life_tmp/acl-ancestor/nested/home" ]] || chmod -N "$life_tmp/acl-ancestor/nested/home"; [[ ! -d "$life_tmp/acl-ancestor" ]] || chmod -N "$life_tmp/acl-ancestor"; rm -rf "$life_tmp"' EXIT
  printf '%s\n' '# metadata sentinel' > "$life_tmp/home/.profile"
  xattr -w user.tailmux-test metadata-sentinel "$life_tmp/home/.profile"
  expected="$(xattr -lx "$life_tmp/home/.profile")"
  lifecycle_run install
  lifecycle_success
  [[ "$(xattr -lx "$life_tmp/home/.profile")" == "$expected" ]] || fail 'install lost macOS xattrs'
  lifecycle_run uninstall
  lifecycle_success
  [[ "$(xattr -lx "$life_tmp/home/.profile")" == "$expected" ]] || fail 'uninstall lost macOS xattrs'
  chmod +a "$USER allow read" "$life_tmp/home/.profile"
  cp -p "$life_tmp/home/.profile" "$life_tmp/before"
  lifecycle_run install
  lifecycle_refusal 'RC ACLs are refused'
  cmp -s "$life_tmp/before" "$life_tmp/home/.profile" || fail 'ACL refusal modified RC'
  chmod -N "$life_tmp/home/.profile"
  chmod +a "$USER allow write" "$life_tmp/home"
  lifecycle_run install
  lifecycle_refusal 'Unknown or mutating RC ancestor ACLs are refused'
  mkdir "$life_tmp/home/nested"
  life_status=0
  life_out="$(env HOME="$life_tmp/home/nested" ZDOTDIR="$life_tmp/home/nested" SHELL=/bin/bash \
    PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" install 2>&1)" || life_status=$?
  lifecycle_refusal 'Unknown or mutating RC ancestor ACLs are refused'
  [[ -z "$(ls -A "$life_tmp/home/nested")" ]] || fail 'ancestor ACL refusal created files'
  chmod -N "$life_tmp/home"
  mkdir -p "$life_tmp/acl-ancestor/nested/home"
  chmod +a 'everyone allow delete_child,add_subdirectory' "$life_tmp/acl-ancestor"
  for operation in install uninstall; do
    life_status=0
    life_out="$(env HOME="$life_tmp/acl-ancestor/nested/home" ZDOTDIR="$life_tmp/acl-ancestor/nested/home" SHELL=/bin/bash \
      PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" "$operation" 2>&1)" || life_status=$?
    lifecycle_refusal 'Unknown or mutating RC ancestor ACLs are refused'
    [[ -z "$(ls -A "$life_tmp/acl-ancestor/nested/home")" ]] || fail 'higher mutating ACL refusal created files'
  done
  chmod -N "$life_tmp/acl-ancestor"
  chmod +a 'everyone deny delete' "$life_tmp/acl-ancestor"
  chmod +a 'everyone deny delete' "$life_tmp/acl-ancestor/nested/home"
  acl_before="$(ls -lde "$life_tmp/acl-ancestor")"
  acl_before="${acl_before#*$'\n'}"
  acl_home_before="$(ls -lde "$life_tmp/acl-ancestor/nested/home")"
  acl_home_before="${acl_home_before#*$'\n'}"
  for operation in install uninstall; do
    life_status=0
    life_out="$(env HOME="$life_tmp/acl-ancestor/nested/home" ZDOTDIR="$life_tmp/acl-ancestor/nested/home" SHELL=/bin/bash \
      PATH="$life_bin" FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" "$operation" 2>&1)" || life_status=$?
    lifecycle_success
  done
  acl_after="$(ls -lde "$life_tmp/acl-ancestor")"
  [[ "${acl_after#*$'\n'}" == "$acl_before" ]] || fail 'higher deny-only ACL changed'
  acl_after="$(ls -lde "$life_tmp/acl-ancestor/nested/home")"
  [[ "${acl_after#*$'\n'}" == "$acl_home_before" ]] || fail 'direct deny-only ACL changed'
  [[ ! -s "$life_tmp/forbidden" ]] || fail 'metadata test invoked forbidden process'
  pass 'macOS xattrs survive; RC/unknown/mutating ancestor ACLs refuse; default deny-delete directory ACLs survive'

)

test_lifecycle_environment_paths() (
  local life_tmp life_bin life_status=0 life_out='' field invalid operation home_path zsh_path shell
  lifecycle_fixture
  trap 'rm -rf "$life_tmp"' EXIT
  mkdir "$life_tmp/victim"
  source "$REPO_ROOT/scripts/lib/constants.sh"
  printf '%s\n%s\n%s\n' "$TAILMUX_BLOCK_BEGIN" "$TAILMUX_FUNC" "$TAILMUX_BLOCK_END" > "$life_tmp/victim/.bashrc"
  cp "$life_tmp/victim/.bashrc" "$life_tmp/victim/.zshrc"
  cp "$life_tmp/victim/.bashrc" "$life_tmp/before"
  find "$life_tmp/home" "$life_tmp/victim" -print | sort > "$life_tmp/before-paths"
  for field in HOME ZDOTDIR; do
    for invalid in "$life_tmp/absent"$'\n'"$life_tmp/victim" 'relative dir'; do
      for operation in install uninstall; do
        home_path="$life_tmp/home"
        zsh_path="$life_tmp/home"
        if [[ "$field" == HOME ]]; then home_path="$invalid"; else zsh_path="$invalid"; fi
        life_status=0
        life_out="$(env HOME="$home_path" ZDOTDIR="$zsh_path" SHELL=/bin/bash PATH="$life_bin" \
          FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" "$operation" 2>&1)" || life_status=$?
        lifecycle_refusal 'HOME and ZDOTDIR must be absolute paths without newlines'
        cmp -s "$life_tmp/victim/.bashrc" "$life_tmp/before" || fail 'invalid environment changed Bash RC bytes'
        cmp -s "$life_tmp/victim/.zshrc" "$life_tmp/before" || fail 'invalid environment changed Zsh RC bytes'
        find "$life_tmp/home" "$life_tmp/victim" -print | sort > "$life_tmp/after-paths"
        cmp -s "$life_tmp/before-paths" "$life_tmp/after-paths" || fail 'invalid environment created or removed files'
        [[ ! -s "$life_tmp/forbidden" ]] || fail 'invalid environment invoked forbidden command'
      done
    done
  done
  mkdir "$life_tmp/home space" "$life_tmp/zsh space"
  for shell in /bin/bash /bin/zsh; do
    for operation in install uninstall; do
      life_status=0
      life_out="$(env HOME="$life_tmp/home space" ZDOTDIR="$life_tmp/zsh space" SHELL="$shell" PATH="$life_bin" \
        FORBIDDEN_TRACE="$life_tmp/forbidden" /bin/bash "$SETUP_SCRIPT" "$operation" 2>&1)" || life_status=$?
      lifecycle_success
    done
  done
  [[ ! -s "$life_tmp/forbidden" ]] || fail 'space-path control invoked forbidden command'
  pass 'whole HOME/ZDOTDIR paths reject newlines and relative input without writes; spaces work in Bash and Zsh'
)

run_installer_lifecycle_suite() {
  test_lifecycle_environment_paths
  test_lifecycle_offline_dispatch
  test_lifecycle_bootstrap_refusal
  test_lifecycle_repeatability
  test_lifecycle_missing_tailscale
  test_lifecycle_ownership_refusals
  test_lifecycle_modified_and_multifile
  test_lifecycle_symlink_and_permissions
  test_lifecycle_write_failures
  test_lifecycle_zsh_and_legacy_taildrive
  test_lifecycle_legacy_upgrade_and_byte_boundaries
  test_lifecycle_lock_and_readonly
  test_lifecycle_macos_metadata
}
