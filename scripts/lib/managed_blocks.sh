# shellcheck shell=bash
# Shared managed block lifecycle helpers

managed_block_prepare_install() {
  local entity_label="${1:?missing entity label}"
  local block_begin="${2:?missing block begin marker}"
  local block_end="${3:?missing block end marker}"
  local installed_check_fn="${4:?missing installed check function}"
  local state

  touch "$RC_FILE"
  state="$(managed_block_state "$block_begin" "$block_end")"

  if [[ "$state" == "malformed" ]]; then
    print_warning "$entity_label managed block is malformed in $RC_FILE; no changes made"
    return 20
  fi

  if [[ "$state" == "valid" ]]; then
    if "$installed_check_fn"; then
      print_success "$entity_label already in $RC_FILE"
      return 10
    fi
    print_step "Refreshing incomplete $entity_label managed block in $RC_FILE"
    if ! remove_managed_block "$block_begin" "$block_end"; then
      print_warning "Could not safely refresh incomplete $entity_label managed block in $RC_FILE; no changes made"
      return 20
    fi
  elif "$installed_check_fn"; then
    print_success "$entity_label already in $RC_FILE"
    return 10
  fi

  return 0
}

managed_block_remove() {
  local entity_title="${1:?missing entity title}"
  local entity_label="${2:?missing entity label}"
  local managed_block_label="${3:?missing managed block label}"
  local block_begin="${4:?missing block begin marker}"
  local block_end="${5:?missing block end marker}"
  local state

  state="$(managed_block_state "$block_begin" "$block_end")"
  if [[ "$state" == "valid" ]]; then
    print_step "Removing $managed_block_label from $RC_FILE"
    if ! remove_managed_block "$block_begin" "$block_end"; then
      print_warning "$entity_title managed block markers are malformed; no changes made to $RC_FILE"
      return 0
    fi
  elif [[ "$state" == "malformed" ]]; then
    print_warning "$entity_title managed block markers are malformed; no changes made to $RC_FILE"
    return 0
  else
    print_warning "$entity_label not found in $RC_FILE"
    return 0
  fi

  print_success "$entity_label removed from $RC_FILE"
  return 0
}
