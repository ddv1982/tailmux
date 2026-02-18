#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export REPO_ROOT
export SETUP_SCRIPT="$REPO_ROOT/setup.sh"
export TAILMUX_SKIP_MACOS_FILE_SHARING_PREF=1

# shellcheck source=scripts/tests/lib/assert.sh
source "$SCRIPT_DIR/lib/assert.sh"
# shellcheck source=scripts/tests/lib/fakes.sh
source "$SCRIPT_DIR/lib/fakes.sh"
# shellcheck source=scripts/tests/lib/legacy_cases.sh
source "$SCRIPT_DIR/lib/legacy_cases.sh"

AVAILABLE_SUITES=(
  syntax_lint
  core_install
  core_resolver_security
  extended_macos_states
  extended_update_branches
  extended_taildrive_runtime
  extended_uninstall_edges
)

QUICK_SUITES=(
  core_install
  core_resolver_security
)

FULL_SUITES=(
  syntax_lint
  core_install
  core_resolver_security
  extended_macos_states
  extended_update_branches
  extended_taildrive_runtime
  extended_uninstall_edges
)

print_usage() {
  cat <<USAGE
Usage: scripts/tests/run.sh <command>

Commands:
  lint                 Run syntax and shellcheck validation suite
  quick                Run required core suites
  full                 Run all suites (core + extended)
  suite <suite_name>   Run one suite by name
  list                 List suite names
USAGE
}

load_suite() {
  local suite_name="${1:?missing suite name}"

  case "$suite_name" in
    syntax_lint)
      if ! declare -f run_syntax_lint_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/syntax_lint.sh
        source "$SCRIPT_DIR/suites/syntax_lint.sh"
      fi
      ;;
    core_install)
      if ! declare -f run_core_install_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/core_install.sh
        source "$SCRIPT_DIR/suites/core_install.sh"
      fi
      ;;
    core_resolver_security)
      if ! declare -f run_core_resolver_security_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/core_resolver_security.sh
        source "$SCRIPT_DIR/suites/core_resolver_security.sh"
      fi
      ;;
    extended_macos_states)
      if ! declare -f run_extended_macos_states_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/extended_macos_states.sh
        source "$SCRIPT_DIR/suites/extended_macos_states.sh"
      fi
      ;;
    extended_update_branches)
      if ! declare -f run_extended_update_branches_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/extended_update_branches.sh
        source "$SCRIPT_DIR/suites/extended_update_branches.sh"
      fi
      ;;
    extended_taildrive_runtime)
      if ! declare -f run_extended_taildrive_runtime_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/extended_taildrive_runtime.sh
        source "$SCRIPT_DIR/suites/extended_taildrive_runtime.sh"
      fi
      ;;
    extended_uninstall_edges)
      if ! declare -f run_extended_uninstall_edges_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/extended_uninstall_edges.sh
        source "$SCRIPT_DIR/suites/extended_uninstall_edges.sh"
      fi
      ;;
    *)
      fail "unknown suite: $suite_name"
      ;;
  esac
}

run_suite() {
  local suite_name="${1:?missing suite name}"
  local fn_name="run_${suite_name}_suite"
  load_suite "$suite_name"

  if ! declare -f "$fn_name" >/dev/null 2>&1; then
    fail "unknown suite: $suite_name"
  fi

  echo ""
  echo "==> Suite: $suite_name"
  "$fn_name"
}

run_many() {
  local suite_name
  for suite_name in "$@"; do
    run_suite "$suite_name"
  done
}

main() {
  local command="${1:-full}"

  case "$command" in
    lint)
      run_many "syntax_lint"
      ;;
    quick)
      run_many "${QUICK_SUITES[@]}"
      ;;
    full)
      run_many "${FULL_SUITES[@]}"
      ;;
    suite)
      shift || true
      if [[ $# -ne 1 ]]; then
        fail "suite command requires exactly one suite name"
      fi
      run_suite "$1"
      ;;
    list)
      printf '%s\n' "${AVAILABLE_SUITES[@]}"
      ;;
    --help|-h|help)
      print_usage
      ;;
    *)
      fail "unknown command: $command"
      ;;
  esac

  echo ""
  echo "All requested suites passed."
}

main "$@"
