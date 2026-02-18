#!/usr/bin/env bash

test_tailmux_alias_precedence_over_tailnet_json() {
  local tmp
  local fake_bin
  local hosts_file
  local ssh_calls
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  hosts_file="$tmp/home/hosts"
  ssh_calls="$tmp/home/ssh.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  cat > "$hosts_file" <<'HOSTS'
home 100.64.0.99
HOSTS

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" TAILMUX_HOSTS_FILE="$hosts_file" bash -c 'source "$HOME/.profile"; tailmux home' 2>&1)"
  [[ "$out" == *"user-alias"* ]] || fail "expected user-alias resolution mode"
  assert_contains "$ssh_calls" '100\.64\.0\.99'
  pass "tailmux alias precedence over tailnet json"
}

test_tailmux_status_json_matches_short_and_fqdn() {
  local tmp
  local fake_bin
  local ssh_calls
  local out_short
  local out_fqdn

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  ssh_calls="$tmp/home/ssh.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${TAILSCALE_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$TAILSCALE_CALLS_FILE"
fi
if [[ "${1:-}" == "status" && "${2:-}" == "--json" ]]; then
  printf '%s\n' '{"BackendState":"Running","MagicDNSSuffix":"example.ts.net.","Self":{"HostName":"self","DNSName":"self.example.ts.net.","TailscaleIPs":["100.64.0.1"]},"Peer":{"abc":{"HostName":"laptop","DNSName":"laptop.example.ts.net.","TailscaleIPs":["100.64.0.2"]}}}'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  exit 0
fi
if [[ "${1:-}" == "set" || "${1:-}" == "up" || "${1:-}" == "drive" ]]; then
  exit 0
fi
if [[ "${1:-}" == "dns" ]]; then
  exit 1
fi
if [[ "${1:-}" == "debug" && "${2:-}" == "prefs" ]]; then
  printf '{"CorpDNS":true}\n'
  exit 0
fi
exit 0
BIN
  chmod +x "$fake_bin/tailscale"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  out_short="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux laptop' 2>&1)"
  [[ "$out_short" == *"tailnet-json"* ]] || fail "expected tailnet-json mode for short hostname"

  out_fqdn="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux laptop.example.ts.net' 2>&1)"
  [[ "$out_fqdn" == *"tailnet-json"* ]] || fail "expected tailnet-json mode for FQDN"

  assert_occurrences "$ssh_calls" '100\.64\.0\.2' 2
  pass "tailmux status json matches short and fqdn"
}

test_tailmux_dns_fallback_when_json_misses() {
  local tmp
  local fake_bin
  local ssh_calls
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  ssh_calls="$tmp/home/ssh.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "status" && "${2:-}" == "--json" ]]; then
  printf '%s\n' '{"BackendState":"Running","MagicDNSSuffix":"example.ts.net.","Self":{"HostName":"self","DNSName":"self.example.ts.net.","TailscaleIPs":["100.64.0.1"]},"Peer":{}}'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  exit 0
fi
if [[ "${1:-}" == "dns" && "${2:-}" == "query" ]]; then
  printf '%s\n' 'office.example.ts.net. 1m IN TypeA 100.64.0.88'
  exit 0
fi
if [[ "${1:-}" == "set" || "${1:-}" == "up" || "${1:-}" == "drive" ]]; then
  exit 0
fi
if [[ "${1:-}" == "debug" && "${2:-}" == "prefs" ]]; then
  printf '{"CorpDNS":true}\n'
  exit 0
fi
exit 0
BIN
  chmod +x "$fake_bin/tailscale"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" USER=tailuser TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux office' 2>&1)"
  [[ "$out" == *"tailnet-dns"* ]] || fail "expected tailnet-dns mode when json misses"
  assert_contains "$ssh_calls" '100\.64\.0\.88'
  pass "tailmux dns fallback when json misses"
}

test_tailmux_lan_fallback_requires_flag() {
  local tmp
  local fake_bin
  local ssh_calls
  local out_default
  local out_lan

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  ssh_calls="$tmp/home/ssh.calls"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/getent" <<'BIN'
#!/usr/bin/env bash
if [[ "${1:-}" == "ahostsv4" && "${2:-}" == "box.local" ]]; then
  printf '%s\n' '192.168.1.20 STREAM box.local'
  exit 0
fi
exit 2
BIN
  cat > "$fake_bin/dscacheutil" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN
  cat > "$fake_bin/nslookup" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN
  chmod +x "$fake_bin/getent" "$fake_bin/dscacheutil" "$fake_bin/nslookup"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  out_default="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" bash -c 'source "$HOME/.profile"; tailmux box' 2>&1)"
  [[ "$out_default" == *"passthrough"* ]] || fail "expected passthrough when LAN fallback disabled"
  assert_contains "$ssh_calls" ' box '

  : > "$ssh_calls"
  out_lan="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" SSH_CALLS_FILE="$ssh_calls" TAILMUX_LAN_FALLBACK=1 bash -c 'source "$HOME/.profile"; tailmux box' 2>&1)"
  [[ "$out_lan" == *"lan-local"* ]] || fail "expected lan-local mode when fallback enabled"
  assert_contains "$ssh_calls" '192\.168\.1\.20'
  pass "tailmux LAN fallback requires flag"
}

test_tailmux_doctor_recommendation_on_passthrough() {
  local tmp
  local fake_bin
  local out

  tmp="$(mktemp -d)"
  fake_bin="$tmp/bin"
  mkdir -p "$fake_bin" "$tmp/home"
  make_fake_bin "$fake_bin"

  cat > "$fake_bin/getent" <<'BIN'
#!/usr/bin/env bash
exit 2
BIN
  cat > "$fake_bin/dscacheutil" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN
  cat > "$fake_bin/nslookup" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN
  chmod +x "$fake_bin/getent" "$fake_bin/dscacheutil" "$fake_bin/nslookup"

  HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" TAILMUX_OS_OVERRIDE=Linux TAILMUX_USE_LOCAL_MODULES=1 bash "$SETUP_SCRIPT" install <<'INP' >/dev/null
y
n
INP

  out="$(HOME="$tmp/home" SHELL=/bin/bash PATH="$fake_bin:$PATH" bash -c 'source "$HOME/.profile"; tailmux doctor ghost-host' 2>&1)"
  [[ "$out" == *"recommendation:"* ]] || fail "expected recommendation block on passthrough"
  [[ "$out" == *"tailscale dns status --all"* ]] || fail "expected tailscale dns status hint"
  pass "tailmux doctor recommendation on passthrough"
}

run_core_resolver_security_suite() {
  test_tailmux_rejects_option_target
  test_tailmux_resolver_ip_passthrough
  test_tailmux_alias_precedence_over_tailnet_json
  test_tailmux_status_json_matches_short_and_fqdn
  test_tailmux_dns_fallback_when_json_misses
  test_tailmux_lan_fallback_requires_flag
  test_tailmux_doctor_recommendation_on_passthrough
}
