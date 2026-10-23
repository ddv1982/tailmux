#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
files=("$REPO_ROOT/setup.sh" "$REPO_ROOT/install.sh" "$REPO_ROOT/bin/tailmux")
while IFS= read -r file; do files+=("$file"); done < <(find "$REPO_ROOT/scripts" -name '*.sh' -type f | sort)
for file in "${files[@]}"; do bash -n "$file"; done
shellcheck -x "${files[@]}"
printf '%s\n' 'Bash syntax and ShellCheck passed, including bin/tailmux.'
