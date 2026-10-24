# shellcheck shell=bash
LIFECYCLE_CONTEXT=()
LIFECYCLE_ACQUISITION_LOCK=''

validate_prefix() {
  local prefix="$1" component="$1" uid mode platform="${2:-$(uname -s)}"
  [[ "$prefix" == /* && "$prefix" != / && "$prefix" != *$'\n'* && "$prefix" != *$'\r'* &&
    "$prefix" != *'/../'* && "$prefix" != */.. && "$prefix" != *'/./'* && "$prefix" != */. && "$prefix" != */ ]] || {
    rc_error 'Prefix must be an absolute directory path without dot components or line breaks' "$prefix"; return 1;
  }
  while [[ ! -e "$component" && ! -L "$component" ]]; do component=${component%/*}; [[ -n "$component" ]] || component=/; done
  [[ -d "$component" ]] || { rc_error 'Prefix ancestor is not a directory' "$component"; return 1; }
  validate_rc_path "$component/.tailmux-path-check" / "$platform" || return 1
  read -r uid _ mode _ < <(rc_metadata "$component" "$platform")
  if [[ "$uid" != "$UID" || ! "$mode" =~ ^[0-7]+$ ]] || (( (8#$mode & 0022) != 0 )); then
    rc_error 'Prefix ancestor must be privately writable and current-user owned' "$component"; return 1;
  fi
}

lifecycle_file() {
  local path="$1" limit="${2:-0}" expected_mode="${3:-}" platform="${LIFECYCLE_CONTEXT[1]:-$(uname -s)}"
  [[ -f "$path" && ! -L "$path" ]] || return 1
  validate_rc_path "$path" "${LIFECYCLE_CONTEXT[0]:-/}" "$platform" &&
    validate_rc_metadata "$path" "$platform" "$limit" "$expected_mode"
}

installation_receipt() {
  local path="$1" prefix="$2" with_digest="${3:-false}" line digest
  RECEIPT_BINARY_DIGEST='' RECEIPT_CONTENT_DIGEST=''
  lifecycle_file "$path" 16384 || return 1
  { IFS= read -r line; IFS= read -r line; IFS= read -r RECEIPT_BINARY_DIGEST; } < "$path" || return 1
  [[ "$RECEIPT_BINARY_DIGEST" =~ ^[a-f0-9]{64}$ ]] &&
    cmp -s "$path" <(printf 'tailmux-receipt-v1\n%s/tailmux\n%s\n' "$prefix" "$RECEIPT_BINARY_DIGEST") || return 1
  if [[ "$with_digest" == true ]]; then
    digest="$(content_digest < "$path")" || return 1
    RECEIPT_CONTENT_DIGEST=${digest%% *}
  fi
}

installation_digest() {
  local digest
  lifecycle_file "$1" || return 1
  digest="$(content_digest < "$1")" || return 1
  digest=${digest%% *}
  [[ "$digest" =~ ^[a-f0-9]{64}$ ]] || return 1
  printf '%s\n' "$digest"
}

transaction_basename() {
  local LC_ALL=C
  [[ ${#1} -ge 1 && ${#1} -le 96 && "$1" != . && "$1" != .. && "$1" != *[!a-zA-Z0-9._-]* ]]
}

transaction_record() {
  printf 'tailmux-transaction-v1\nid=%s\noperation=%s\nphase=%s\nprefix-sha256=%s\nbefore-binary-sha256=%s\nbefore-receipt-sha256=%s\nafter-binary-sha256=%s\nafter-receipt-sha256=%s\nbackup=%s\nstage=%s\n' \
    "$TX_ID" "$TX_OPERATION" "$TX_PHASE" "$TX_PREFIX_DIGEST" "$TX_BEFORE_BINARY" "$TX_BEFORE_RECEIPT" \
    "$TX_AFTER_BINARY" "$TX_AFTER_RECEIPT" "$TX_BACKUP" "$TX_STAGE"
}

transaction_read() {
  local prefix="$1" field line
  local fields=(TX_ID TX_OPERATION TX_PHASE TX_PREFIX_DIGEST TX_BEFORE_BINARY TX_BEFORE_RECEIPT TX_AFTER_BINARY TX_AFTER_RECEIPT TX_BACKUP TX_STAGE)
  local keys=(id operation phase prefix-sha256 before-binary-sha256 before-receipt-sha256 after-binary-sha256 after-receipt-sha256 backup stage)
  local index=0
  lifecycle_file "$prefix/.tailmux-transaction" 16384 600 || return 1
  {
    IFS= read -r line && [[ "$line" == tailmux-transaction-v1 ]] || return 1
    for field in "${fields[@]}"; do
      IFS= read -r line && [[ "$line" == "${keys[$index]}="* ]] || return 1
      printf -v "$field" '%s' "${line#*=}"
      index=$((index + 1))
    done
  } < "$prefix/.tailmux-transaction"
  transaction_basename "$TX_ID" && transaction_basename "$TX_BACKUP" && transaction_basename "$TX_STAGE" || return 1
  [[ "$TX_BACKUP" == .tailmux-backup.?* && "$TX_STAGE" == .tailmux-stage.?* ]] || return 1
  case "$TX_OPERATION" in replace-owned|recover-modified) ;; *) return 1 ;; esac
  case "$TX_PHASE" in prepared|binary-published|committed) ;; *) return 1 ;; esac
  for field in "$TX_PREFIX_DIGEST" "$TX_BEFORE_BINARY" "$TX_BEFORE_RECEIPT" "$TX_AFTER_BINARY" "$TX_AFTER_RECEIPT"; do
    [[ "$field" =~ ^[a-f0-9]{64}$ ]] || return 1
  done
  cmp -s "$prefix/.tailmux-transaction" <(transaction_record)
}

lifecycle_owner_record() {
  printf 'tailmux-lock-v1\nuid=%s\ntransaction=%s\n' "$UID" "$1"
}

lifecycle_owner_matches() {
  local prefix="$1" id="$2"
  lifecycle_directory "$prefix/.tailmux-install-lock" &&
    lifecycle_file "$prefix/.tailmux-install-lock/owner" 256 600 &&
    cmp -s "$prefix/.tailmux-install-lock/owner" <(lifecycle_owner_record "$id")
}

lifecycle_lock() {
  local prefix="$1" id="$2" lock="$1/.tailmux-install-lock"
  (umask 077; mkdir "$lock") || { rc_error 'Installation lifecycle is locked; inspect before retrying' "$lock"; return 1; }
  LIFECYCLE_ACQUISITION_LOCK="$lock"
  trap 'lifecycle_acquisition_exit "$?"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  (umask 077; lifecycle_owner_record "$id" > "$lock/owner") || return 1
  lifecycle_owner_matches "$prefix" "$id"
}

lifecycle_acquisition_exit() {
  local status="$1" lock="$LIFECYCLE_ACQUISITION_LOCK"
  trap - EXIT INT TERM
  if lifecycle_directory "$lock" 700; then
    if [[ -e "$lock/owner" || -L "$lock/owner" ]]; then
      lifecycle_file "$lock/owner" 256 600 && rm "$lock/owner" || exit "$status"
    fi
    rmdir "$lock" || :
  fi
  exit "$status"
}

lifecycle_unlock() {
  lifecycle_owner_matches "$1" "$2" || return 1
  rm "$1/.tailmux-install-lock/owner" && [[ ! -e "$1/.tailmux-install-lock/owner" ]] && rmdir "$1/.tailmux-install-lock"
}

lifecycle_directory() {
  local path="$1" expected_mode="${2:-}" uid mode platform="${LIFECYCLE_CONTEXT[1]:-$(uname -s)}"
  [[ "$path" == /* && "$path" != */ && "$path" != *$'\r'* && -d "$path" && ! -L "$path" ]] || return 1
  validate_rc_path "$path/.tailmux-path-check" "${LIFECYCLE_CONTEXT[0]:-/}" "$platform" || return 1
  read -r uid _ mode _ < <(rc_metadata "$path" "$platform")
  [[ "$uid" == "$UID" && "$mode" =~ ^[0-7]+$ ]] && (( (8#$mode & 0022) == 0 )) || return 1
  [[ -z "$expected_mode" ]] || (( (8#$mode & 07777) == 8#$expected_mode ))
}

transaction_validate() {
  local prefix="$1" digest current receipt backup="$1/$TX_BACKUP" stage="$1/$TX_STAGE"
  local -a LIFECYCLE_CONTEXT=("" "$(uname -s)")
  validate_prefix "$prefix" "${LIFECYCLE_CONTEXT[1]}" || return 1
  LIFECYCLE_CONTEXT[0]="$prefix"
  digest="$(printf '%s' "$prefix" | content_digest)" || return 1
  [[ "${digest%% *}" == "$TX_PREFIX_DIGEST" ]] || return 1
  if [[ -e "$prefix/.tailmux-install-lock" || -L "$prefix/.tailmux-install-lock" ]]; then
    lifecycle_owner_matches "$prefix" "$TX_ID" || return 1
  fi
  lifecycle_directory "$backup" 700 && lifecycle_directory "$stage" 700 || return 1
  [[ -x "$backup/tailmux" && -x "$stage/candidate" && -x "$prefix/tailmux" ]] || return 1
  [[ "$(installation_digest "$backup/tailmux")" == "$TX_BEFORE_BINARY" &&
    "$(installation_digest "$stage/candidate")" == "$TX_AFTER_BINARY" ]] || return 1
  installation_receipt "$backup/receipt" "$prefix" true && [[ "$RECEIPT_CONTENT_DIGEST" == "$TX_BEFORE_RECEIPT" ]] || return 1
  [[ "$TX_OPERATION" != replace-owned || "$RECEIPT_BINARY_DIGEST" == "$TX_BEFORE_BINARY" ]] || return 1
  installation_receipt "$stage/candidate-receipt" "$prefix" true &&
    [[ "$RECEIPT_BINARY_DIGEST" == "$TX_AFTER_BINARY" && "$RECEIPT_CONTENT_DIGEST" == "$TX_AFTER_RECEIPT" ]] || return 1
  installation_receipt "$prefix/.tailmux-receipt" "$prefix" true || return 1
  receipt="$RECEIPT_CONTENT_DIGEST"
  current="$(installation_digest "$prefix/tailmux")" || return 1
  case "$current:$receipt" in
    "$TX_BEFORE_BINARY:$TX_BEFORE_RECEIPT"|"$TX_AFTER_BINARY:$TX_BEFORE_RECEIPT"|"$TX_AFTER_BINARY:$TX_AFTER_RECEIPT") return 0 ;;
    *) return 1 ;;
  esac
}

inspect_installation() {
  local prefix="$1" binary="$1/tailmux" receipt="$1/.tailmux-receipt"
  local -a LIFECYCLE_CONTEXT=("" "$(uname -s)")
  INSTALL_STATE=unsafe INSTALL_PREFIX="$prefix" INSTALL_CURRENT_DIGEST='' INSTALL_RECEIPT_DIGEST='' INSTALL_TRANSACTION=''
  validate_prefix "$prefix" "${LIFECYCLE_CONTEXT[1]}" || return 0
  if [[ -d "$prefix" ]]; then LIFECYCLE_CONTEXT[0]="$prefix"; fi
  if [[ -e "$prefix/.tailmux-transaction" || -L "$prefix/.tailmux-transaction" ]]; then
    if transaction_read "$prefix" && transaction_validate "$prefix"; then
      INSTALL_STATE=pending INSTALL_TRANSACTION="$TX_ID"
      INSTALL_CURRENT_DIGEST="$(installation_digest "$binary")"
      installation_receipt "$receipt" "$prefix" || return 0
      INSTALL_RECEIPT_DIGEST="$RECEIPT_BINARY_DIGEST"
    fi
    return 0
  fi
  if [[ -e "$binary" || -L "$binary" ]]; then
    [[ -f "$binary" && ! -L "$binary" ]] || return 0
    INSTALL_CURRENT_DIGEST="$(installation_digest "$binary")" || return 0
  fi
  if [[ ! -e "$receipt" && ! -L "$receipt" ]]; then
    if [[ ! -e "$binary" && ! -L "$binary" ]]; then INSTALL_STATE=absent; else INSTALL_STATE=foreign; fi
    return 0
  fi
  [[ -f "$receipt" && ! -L "$receipt" ]] || return 0
  lifecycle_file "$receipt" 16384 || return 0
  INSTALL_STATE=foreign
  installation_receipt "$receipt" "$prefix" || return 0
  INSTALL_RECEIPT_DIGEST="$RECEIPT_BINARY_DIGEST"
  if [[ -e "$binary" && ! -x "$binary" ]]; then INSTALL_STATE=unsafe; return 0; fi
  if [[ ! -e "$binary" && ! -L "$binary" ]]; then INSTALL_STATE='receipt-only'
  elif [[ "$INSTALL_CURRENT_DIGEST" == "$INSTALL_RECEIPT_DIGEST" ]]; then INSTALL_STATE=owned
  else INSTALL_STATE=modified; fi
}

require_installation() {
  inspect_installation "$TAILMUX_PREFIX"
  if [[ -e "$TAILMUX_PREFIX/.tailmux-install-lock" || -L "$TAILMUX_PREFIX/.tailmux-install-lock" ]]; then
    if [[ "$INSTALL_STATE" == pending ]]; then
      rc_error "Pending transaction $INSTALL_TRANSACTION; lifecycle is locked; preserve artifacts for reviewed recovery" "$TAILMUX_PREFIX"
    else
      rc_error 'Installation lifecycle is locked; inspect before retrying' "$TAILMUX_PREFIX/.tailmux-install-lock"
    fi
    return 1
  fi
  installation_allowed
}

installation_allowed() {
  case "$INSTALL_STATE" in
    absent|owned|receipt-only) return 0 ;;
    modified) rc_error 'Refusing modified installation; valid receipt does not match executable' "$INSTALL_PREFIX" ;;
    foreign) rc_error 'Foreign installation; receipt is missing or malformed' "$INSTALL_PREFIX" ;;
    pending) rc_error "Pending transaction $INSTALL_TRANSACTION; preserve artifacts for reviewed recovery" "$INSTALL_PREFIX" ;;
    unsafe) rc_error 'Unsafe installation or transaction metadata; inspect without changing artifacts' "$INSTALL_PREFIX" ;;
  esac
  return 1
}

transaction_write() {
  local prefix="$1" phase="$2"
  lifecycle_owner_matches "$prefix" "$TX_ID" || return 1
  TX_PHASE="$phase"
  (umask 077; transaction_record > "$prefix/$TX_STAGE/transaction") &&
    chmod 600 "$prefix/$TX_STAGE/transaction" &&
    mv "$prefix/$TX_STAGE/transaction" "$prefix/.tailmux-transaction" &&
    lifecycle_file "$prefix/.tailmux-transaction" 16384 600 &&
    cmp -s "$prefix/.tailmux-transaction" <(transaction_record)
}

transaction_remove_stage() {
  local stage="$1"
  [[ -n "$stage" ]] || return 0
  rm -f "$stage/tailmux" "$stage/receipt" "$stage/candidate" "$stage/candidate-receipt" "$stage/transaction" "$stage/rollback-binary" "$stage/rollback-receipt" && rmdir "$stage"
}

transaction_clear() {
  local prefix="$1"
  lifecycle_owner_matches "$prefix" "$TX_ID" || return 1
  rm "$prefix/.tailmux-transaction" && [[ ! -e "$prefix/.tailmux-transaction" && ! -L "$prefix/.tailmux-transaction" ]]
}

transaction_restore_receipt_then_binary() {
  local prefix="$1" stage backup
  local -a LIFECYCLE_CONTEXT=("" "$(uname -s)")
  validate_prefix "$prefix" "${LIFECYCLE_CONTEXT[1]}" || return 1
  LIFECYCLE_CONTEXT[0]="$prefix"
  transaction_read "$prefix" && [[ -d "$prefix/.tailmux-install-lock" ]] && transaction_validate "$prefix" || return 1
  stage="$prefix/$TX_STAGE" backup="$prefix/$TX_BACKUP"
  if [[ "$(installation_digest "$prefix/.tailmux-receipt")" != "$TX_BEFORE_RECEIPT" ]]; then
    cp "$backup/receipt" "$stage/rollback-receipt" && chmod 600 "$stage/rollback-receipt" &&
      cmp -s "$backup/receipt" "$stage/rollback-receipt" &&
      mv "$stage/rollback-receipt" "$prefix/.tailmux-receipt" || return 1
    [[ "$(installation_digest "$prefix/.tailmux-receipt")" == "$TX_BEFORE_RECEIPT" ]] || return 1
  fi
  if [[ "$(installation_digest "$prefix/tailmux")" != "$TX_BEFORE_BINARY" ]]; then
    cp "$backup/tailmux" "$stage/rollback-binary" && chmod 755 "$stage/rollback-binary" &&
      cmp -s "$backup/tailmux" "$stage/rollback-binary" &&
      mv "$stage/rollback-binary" "$prefix/tailmux" || return 1
  fi
  [[ -x "$prefix/tailmux" && "$(installation_digest "$prefix/tailmux")" == "$TX_BEFORE_BINARY" &&
    "$(installation_digest "$prefix/.tailmux-receipt")" == "$TX_BEFORE_RECEIPT" ]] || return 1
  transaction_clear "$prefix"
}

transaction_publish() {
  local prefix="$1" stage="$1/$TX_STAGE"
  local -a LIFECYCLE_CONTEXT=("" "$(uname -s)")
  validate_prefix "$prefix" "${LIFECYCLE_CONTEXT[1]}" || return 1
  LIFECYCLE_CONTEXT[0]="$prefix"
  [[ -d "$prefix/.tailmux-install-lock" ]] && transaction_validate "$prefix" || return 1
  if [[ "$(installation_digest "$prefix/tailmux")" != "$TX_AFTER_BINARY" ]]; then
    cp "$stage/candidate" "$stage/tailmux" && chmod 755 "$stage/tailmux" &&
      cmp -s "$stage/candidate" "$stage/tailmux" && mv "$stage/tailmux" "$prefix/tailmux" || return 1
    [[ "$(installation_digest "$prefix/tailmux")" == "$TX_AFTER_BINARY" && -x "$prefix/tailmux" ]] || return 1
  fi
  transaction_write "$prefix" binary-published || return 1
  if [[ "$(installation_digest "$prefix/.tailmux-receipt")" != "$TX_AFTER_RECEIPT" ]]; then
    cp "$stage/candidate-receipt" "$stage/receipt" && chmod 600 "$stage/receipt" &&
      cmp -s "$stage/candidate-receipt" "$stage/receipt" && mv "$stage/receipt" "$prefix/.tailmux-receipt" || return 1
  fi
  transaction_validate "$prefix" &&
    [[ "$(installation_digest "$prefix/.tailmux-receipt")" == "$TX_AFTER_RECEIPT" ]] || return 1
  transaction_write "$prefix" committed
}

replacement_exit() {
  local status="$1" prefix="$2" id="$3" stage="$4"
  trap - EXIT INT TERM
  if [[ -e "$prefix/.tailmux-transaction" || -L "$prefix/.tailmux-transaction" ]]; then
    if (( status != 0 )) && transaction_restore_receipt_then_binary "$prefix"; then
      printf 'Replacement failed; restored previous client. Backup retained at %s/%s\n' "$prefix" "$TX_BACKUP" >&2
    else
      printf 'Replacement incomplete; preserve transaction %s at %s/.tailmux-transaction and its lock for reviewed recovery.\n' "$id" "$prefix" >&2
      exit 1
    fi
  elif (( status != 0 )); then
    printf 'Replacement did not complete; inspect the client and lifecycle artifacts at %s.\n' "$prefix" >&2
  fi
  if ! transaction_remove_stage "$stage" || ! lifecycle_unlock "$prefix" "$id"; then
    printf 'Lifecycle cleanup incomplete; inspect %s/.tailmux-install-lock before retrying.\n' "$prefix" >&2
    exit 1
  fi
  exit "$status"
}

do_replace_owned() (
  local stage='' id=".tailmux-tx.$$.$RANDOM" digest backup
  local -a LIFECYCLE_CONTEXT=("" "$(uname -s)")
  require_installation || return 1
  [[ "$INSTALL_STATE" == owned ]] || { rc_error 'Replacement requires an existing owned executable' "$TAILMUX_PREFIX"; return 1; }
  lifecycle_lock "$TAILMUX_PREFIX" "$id" || return 1
  trap 'replacement_exit "$?" "$TAILMUX_PREFIX" "$id" "$stage"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  validate_prefix "$TAILMUX_PREFIX" "${LIFECYCLE_CONTEXT[1]}" || return 1
  LIFECYCLE_CONTEXT[0]="$TAILMUX_PREFIX"
  inspect_installation "$TAILMUX_PREFIX"
  installation_allowed && [[ "$INSTALL_STATE" == owned ]] || return 1
  [[ -f "$SCRIPT_DIR/bin/tailmux" && ! -L "$SCRIPT_DIR/bin/tailmux" ]] || return 1
  if cmp -s "$SCRIPT_DIR/bin/tailmux" "$TAILMUX_PREFIX/tailmux"; then
    printf 'Client already installed at %s/tailmux\n' "$TAILMUX_PREFIX"
    return 0
  fi
  TX_PREFIX_DIGEST="$(printf '%s' "$TAILMUX_PREFIX" | content_digest)" || return 1
  TX_PREFIX_DIGEST=${TX_PREFIX_DIGEST%% *}
  [[ "$TX_PREFIX_DIGEST" =~ ^[a-f0-9]{64}$ ]] || return 1
  stage="$(mktemp -d "$TAILMUX_PREFIX/.tailmux-stage.XXXXXX")" || return 1
  cp "$SCRIPT_DIR/bin/tailmux" "$stage/candidate" && chmod 755 "$stage/candidate" &&
    cmp -s "$SCRIPT_DIR/bin/tailmux" "$stage/candidate" || return 1
  digest="$(installation_digest "$stage/candidate")" || return 1
  printf 'tailmux-receipt-v1\n%s/tailmux\n%s\n' "$TAILMUX_PREFIX" "$digest" > "$stage/candidate-receipt" || return 1
  chmod 600 "$stage/candidate-receipt" || return 1
  backup="$(mktemp -d "$TAILMUX_PREFIX/.tailmux-backup.XXXXXX")" || return 1
  cp "$TAILMUX_PREFIX/tailmux" "$backup/tailmux" && chmod 700 "$backup/tailmux" &&
    cp "$TAILMUX_PREFIX/.tailmux-receipt" "$backup/receipt" && chmod 600 "$backup/receipt" || return 1
  TX_ID="$id" TX_OPERATION=replace-owned TX_PHASE=prepared
  TX_BEFORE_BINARY="$INSTALL_CURRENT_DIGEST" TX_AFTER_BINARY="$digest"
  TX_BEFORE_RECEIPT="$(installation_digest "$TAILMUX_PREFIX/.tailmux-receipt")" || return 1
  TX_AFTER_RECEIPT="$(installation_digest "$stage/candidate-receipt")" || return 1
  TX_BACKUP=${backup##*/} TX_STAGE=${stage##*/}
  transaction_validate "$TAILMUX_PREFIX" && transaction_write "$TAILMUX_PREFIX" prepared || return 1
  transaction_publish "$TAILMUX_PREFIX" && transaction_clear "$TAILMUX_PREFIX" || return 1
  transaction_remove_stage "$stage" || return 1
  stage=''
  lifecycle_unlock "$TAILMUX_PREFIX" "$id" || return 1
  trap - EXIT INT TERM
  printf 'Client installed at %s/tailmux. Previous content retained in %s\n' "$TAILMUX_PREFIX" "$backup"
)

preflight_lifecycle() {
  local rc
  validate_prefix "$TAILMUX_PREFIX" || return 1
  inspect_installation "$TAILMUX_PREFIX"
  installation_allowed || return 1
  while IFS= read -r rc; do inspect_rc "$rc" >/dev/null || return 1; done < <(rc_paths)
}

migrate_all_rc() {
  local rc
  while IFS= read -r rc; do migrate_rc "$rc" || return 1; done < <(rc_paths)
}

do_install() (
  local stage='' id=".tailmux-tx.$$.$RANDOM" digest published
  require_installation && preflight_lifecycle || return 1
  [[ -f "$SCRIPT_DIR/bin/tailmux" && ! -L "$SCRIPT_DIR/bin/tailmux" ]] || { rc_error 'Local executable is missing or symlinked' "$SCRIPT_DIR/bin/tailmux"; return 1; }
  (umask 077; mkdir -p "$TAILMUX_PREFIX") || return 1
  validate_prefix "$TAILMUX_PREFIX" || return 1
  lifecycle_lock "$TAILMUX_PREFIX" "$id" || return 1
  trap 'transaction_remove_stage "$stage"; lifecycle_unlock "$TAILMUX_PREFIX" "$id"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  preflight_lifecycle || return 1
  stage="$(mktemp -d "$TAILMUX_PREFIX/.tailmux-stage.XXXXXX")" || return 1
  cp "$SCRIPT_DIR/bin/tailmux" "$stage/tailmux" && chmod 755 "$stage/tailmux" || return 1
  cmp -s "$SCRIPT_DIR/bin/tailmux" "$stage/tailmux" || return 1
  digest="$(installation_digest "$stage/tailmux")" || return 1
  printf 'tailmux-receipt-v1\n%s\n%s\n' "$TAILMUX_PREFIX/tailmux" "$digest" > "$stage/receipt" || return 1
  chmod 600 "$stage/receipt" || return 1
  if [[ -f "$TAILMUX_PREFIX/tailmux" ]]; then
    if ! cmp -s "$TAILMUX_PREFIX/tailmux" "$stage/tailmux"; then
      rc_error 'A different owned version is installed; uninstall it with a reviewed checkout before replacing' "$TAILMUX_PREFIX"; return 1
    fi
  else
    if [[ -f "$TAILMUX_PREFIX/.tailmux-receipt" ]]; then
      cmp -s "$stage/receipt" "$TAILMUX_PREFIX/.tailmux-receipt" || { rc_error 'Interrupted installation belongs to a different source digest' "$TAILMUX_PREFIX"; return 1; }
    else
      mv "$stage/receipt" "$TAILMUX_PREFIX/.tailmux-receipt" || return 1
      cmp -s "$TAILMUX_PREFIX/.tailmux-receipt" <(printf 'tailmux-receipt-v1\n%s\n%s\n' "$TAILMUX_PREFIX/tailmux" "$digest") || { rc_error 'Published receipt verification failed' "$TAILMUX_PREFIX"; return 1; }
    fi
    mv "$stage/tailmux" "$TAILMUX_PREFIX/tailmux" || return 1
    published="$(installation_digest "$TAILMUX_PREFIX/tailmux")" || return 1
    [[ "$published" == "$digest" && -x "$TAILMUX_PREFIX/tailmux" && ! -L "$TAILMUX_PREFIX/tailmux" ]] || { rc_error 'Published executable verification failed' "$TAILMUX_PREFIX"; return 1; }
  fi
  inspect_installation "$TAILMUX_PREFIX"
  installation_allowed || return 1
  migrate_all_rc || return 1
  printf 'Client installed at %s/tailmux\n' "$TAILMUX_PREFIX"
  printf '%s\n' 'Warning: your current shell may shadow bare tailmux with an alias or loaded function. Use the absolute executable path.' \
    'No PATH or shell code was added. Dependencies and destination SSH/tmux configuration remain operator-owned.'
)
