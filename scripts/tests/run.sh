#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export REPO_ROOT
export SETUP_SCRIPT="$REPO_ROOT/setup.sh"

# shellcheck source=scripts/tests/lib/assert.sh
source "$SCRIPT_DIR/lib/assert.sh"
# shellcheck source=scripts/tests/lib/fakes.sh
source "$SCRIPT_DIR/lib/fakes.sh"
# shellcheck source=scripts/tests/lib/legacy_cases.sh
source "$SCRIPT_DIR/lib/legacy_cases.sh"

AVAILABLE_SUITES=(
  syntax_lint
  installer_lifecycle
  core_resolver_security
  security_boundaries
  extended_taildrive_runtime
)

QUICK_SUITES=(
  installer_lifecycle
  core_resolver_security
  security_boundaries
)

FULL_SUITES=(
  syntax_lint
  installer_lifecycle
  core_resolver_security
  security_boundaries
  extended_taildrive_runtime
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
    installer_lifecycle)
      if ! declare -f run_installer_lifecycle_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/installer_lifecycle.sh
        source "$SCRIPT_DIR/suites/installer_lifecycle.sh"
      fi
      ;;
    core_resolver_security)
      if ! declare -f run_core_resolver_security_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/core_resolver_security.sh
        source "$SCRIPT_DIR/suites/core_resolver_security.sh"
      fi
      ;;
    security_boundaries)
      if ! declare -f run_security_boundaries_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/security_boundaries.sh
        source "$SCRIPT_DIR/suites/security_boundaries.sh"
      fi
      ;;
    extended_taildrive_runtime)
      if ! declare -f run_extended_taildrive_runtime_suite >/dev/null 2>&1; then
        # shellcheck source=scripts/tests/suites/extended_taildrive_runtime.sh
        source "$SCRIPT_DIR/suites/extended_taildrive_runtime.sh"
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
