#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export REPO_ROOT
run_suite() {
  case "$1" in
    syntax_lint) bash "$SCRIPT_DIR/suites/syntax_lint.sh" ;;
    direct_install|doctor_cli|release_cli|release_preflight|workflow_policy|acceptance_cli) python3 "$SCRIPT_DIR/suites/$1.py" ;;
    workflow_policy_check) python3 "$REPO_ROOT/scripts/release/check_workflows.py" ;;
    runtime_cli|core_resolver_security) python3 "$SCRIPT_DIR/suites/runtime_cli.py" ;;
    installer_cli|installer_lifecycle) python3 "$SCRIPT_DIR/suites/installer_cli.py" ;;
    *) printf 'Unknown suite: %s\n' "$1" >&2; return 2 ;;
  esac
}
case "${1:-full}" in
  lint) run_suite syntax_lint ;;
  quick) run_suite runtime_cli; run_suite installer_cli ;;
  full) run_suite syntax_lint; run_suite runtime_cli; run_suite installer_cli; run_suite doctor_cli; run_suite release_cli; run_suite direct_install; run_suite release_preflight; run_suite workflow_policy; run_suite acceptance_cli; run_suite workflow_policy_check ;;
  suite) [[ $# == 2 ]] || exit 2; run_suite "$2" ;;
  list) printf '%s\n' syntax_lint runtime_cli installer_cli doctor_cli release_cli direct_install release_preflight workflow_policy acceptance_cli workflow_policy_check ;;
  --help|-h) printf '%s\n' 'Usage: bash scripts/tests/run.sh lint|quick|full|list|suite NAME' ;;
  *) printf '%s\n' 'Unknown test command' >&2; exit 2 ;;
esac
printf '%s\n' 'All requested suites passed.'
