#!/usr/bin/env bash

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

pass() {
  echo "[PASS] $*"
}

assert_contains() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  if ! grep -Eq -- "$pattern" "$file"; then
    fail "Expected pattern '$pattern' in $file"
  fi
}

assert_not_contains() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  if grep -Eq -- "$pattern" "$file"; then
    fail "Did not expect pattern '$pattern' in $file"
  fi
}

assert_count() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  local expected="${3:?missing expected count}"
  local actual
  actual="$(grep -Ec -- "$pattern" "$file" || true)"
  [[ "$actual" == "$expected" ]] || fail "Expected $expected matches for '$pattern' in $file, got $actual"
}

assert_occurrences() {
  local file="${1:?missing file}"
  local pattern="${2:?missing pattern}"
  local expected="${3:?missing expected count}"
  local actual
  actual="$(grep -oE -- "$pattern" "$file" | wc -l | tr -d ' ')"
  [[ "$actual" == "$expected" ]] || fail "Expected $expected occurrences for '$pattern' in $file, got $actual"
}
