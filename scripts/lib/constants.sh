# shellcheck shell=bash
# shellcheck disable=SC2034
# Shared constants
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TAILMUX_FUNC="$(cat <<'EOF'
tailmux() {
  _tailmux_usage() {
    echo "Usage: tailmux <host-or-ip>" >&2
    echo "       tailmux doctor <host-or-ip>" >&2
  }

  _tailmux_has_cmd() {
    command -v "$1" >/dev/null 2>&1
  }

  _tailmux_is_ip() {
    local value="${1:-}"
    if [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
      return 0
    fi
    [[ "$value" == *:* ]]
  }

  _tailmux_status_json() {
    tailscale status --json 2>/dev/null
  }

  _tailmux_magicdns_suffix_from_json() {
    local json="${1:-}"
    if [[ -z "$json" ]]; then
      return 1
    fi
    if _tailmux_has_cmd jq; then
      printf '%s\n' "$json" | jq -r '.MagicDNSSuffix // empty' 2>/dev/null
      return 0
    fi
    if _tailmux_has_cmd python3; then
      printf '%s\n' "$json" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("MagicDNSSuffix") or ""))' 2>/dev/null
      return 0
    fi
    printf '%s\n' "$json" | sed -n 's/.*"MagicDNSSuffix"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
  }

  _tailmux_lookup_ip_in_status_json() {
    local host="${1:?missing host}"
    local host_lc
    local json="${2:-}"
    host_lc="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
    host_lc="${host_lc%.}"

    if [[ -z "$json" ]]; then
      return 1
    fi

    if _tailmux_has_cmd jq; then
      printf '%s\n' "$json" | jq -r --arg host "$host_lc" '
        def norm: ascii_downcase;
        def dns_name: (.DNSName // "" | rtrimstr("."));
        def short_name: (dns_name | split(".")[0]);
        [(.Self // empty)] + ((.Peer // {}) | to_entries | map(.value)) |
        map(select(
          ((.HostName // "" | norm) == $host) or
          ((dns_name | norm) == $host) or
          ((short_name | norm) == $host)
        )) |
        .[0].TailscaleIPs[0] // empty
      ' 2>/dev/null
      return 0
    fi

    if _tailmux_has_cmd python3; then
      printf '%s\n' "$json" | python3 - "$host_lc" <<'PY' 2>/dev/null
import json
import sys

target = (sys.argv[1] or "").rstrip(".").lower()
data = json.load(sys.stdin)
nodes = []
self_node = data.get("Self") or {}
if self_node:
    nodes.append(self_node)
nodes.extend((data.get("Peer") or {}).values())

def dns_variants(node):
    dns = (node.get("DNSName") or "").rstrip(".")
    short = dns.split(".")[0] if dns else ""
    return [
        (node.get("HostName") or ""),
        dns,
        short,
    ]

for node in nodes:
    ips = node.get("TailscaleIPs") or []
    if not ips:
        continue
    for candidate in dns_variants(node):
        if candidate.lower() == target:
            print(ips[0])
            raise SystemExit(0)
print("")
PY
      return 0
    fi

    tailscale status 2>/dev/null | awk -v target="$host_lc" '
      BEGIN { target=tolower(target); }
      NF >= 2 {
        name=tolower($2)
        if (name == target) {
          print $1
          exit
        }
      }
    '
  }

  _tailmux_dns_query_a() {
    local name="${1:?missing dns name}"
    if ! _tailmux_has_cmd tailscale; then
      return 1
    fi
    tailscale dns query "$name" a 2>/dev/null | awk '/TypeA/{print $NF; exit}'
  }

  _tailmux_system_lookup_ip() {
    local name="${1:?missing name}"
    local ip=""

    if _tailmux_has_cmd getent; then
      ip="$(getent ahostsv4 "$name" 2>/dev/null | awk '{print $1; exit}')"
      if [[ -n "$ip" ]]; then
        printf '%s\n' "$ip"
        return 0
      fi
    fi

    if _tailmux_has_cmd dscacheutil; then
      ip="$(dscacheutil -q host -a name "$name" 2>/dev/null | awk '/^ip_address:/{print $2; exit}')"
      if [[ -n "$ip" ]]; then
        printf '%s\n' "$ip"
        return 0
      fi
    fi

    if _tailmux_has_cmd nslookup; then
      ip="$(nslookup "$name" 2>/dev/null | awk '/^Name:/{seen=1; next} seen && /^Address: /{print $2; exit}')"
      if [[ -n "$ip" ]]; then
        printf '%s\n' "$ip"
        return 0
      fi
    fi

    return 1
  }

  _tailmux_alias_lookup() {
    local host="${1:?missing host}"
    local host_lc
    local hosts_file="${TAILMUX_HOSTS_FILE:-$HOME/.config/tailmux/hosts}"

    if [[ ! -f "$hosts_file" ]]; then
      return 1
    fi

    host_lc="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
    awk -v key="$host_lc" '
      /^[[:space:]]*#/ { next }
      NF < 2 { next }
      {
        lhs=tolower($1)
        if (lhs == key) {
          print $2
          exit
        }
      }
    ' "$hosts_file"
  }

  _tailmux_resolve_target() {
    local host="${1:?missing host}"
    local resolved=""
    local mode=""
    local status_json=""
    local magic_suffix=""
    local fqdn=""
    local alias_target=""

    if _tailmux_is_ip "$host"; then
      printf '%s\t%s\n' "$host" "input-ip"
      return 0
    fi

    alias_target="$(_tailmux_alias_lookup "$host" 2>/dev/null || true)"
    if [[ -n "$alias_target" ]]; then
      printf '%s\t%s\n' "$alias_target" "user-alias"
      return 0
    fi

    if _tailmux_has_cmd tailscale; then
      status_json="$(_tailmux_status_json || true)"
      resolved="$(_tailmux_lookup_ip_in_status_json "$host" "$status_json" 2>/dev/null || true)"
      if [[ -n "$resolved" ]]; then
        printf '%s\t%s\n' "$resolved" "tailnet-json"
        return 0
      fi

      magic_suffix="$(_tailmux_magicdns_suffix_from_json "$status_json" 2>/dev/null || true)"
      magic_suffix="${magic_suffix%.}"
      fqdn="$host"
      if [[ "$host" != *.* && -n "$magic_suffix" ]]; then
        fqdn="$host.$magic_suffix"
      fi
      resolved="$(_tailmux_dns_query_a "$fqdn" 2>/dev/null || true)"
      if [[ -n "$resolved" ]]; then
        printf '%s\t%s\n' "$resolved" "tailnet-dns"
        return 0
      fi
    fi

    if [[ "${TAILMUX_LAN_FALLBACK:-0}" == "1" && "$host" != *.* ]]; then
      resolved="$(_tailmux_system_lookup_ip "$host.local" 2>/dev/null || true)"
      if [[ -n "$resolved" ]]; then
        printf '%s\t%s\n' "$resolved" "lan-local"
        return 0
      fi
    fi

    resolved="$(_tailmux_system_lookup_ip "$host" 2>/dev/null || true)"
    if [[ -n "$resolved" ]]; then
      printf '%s\t%s\n' "$resolved" "system-dns"
      return 0
    fi

    printf '%s\t%s\n' "$host" "passthrough"
  }

  _tailmux_doctor() {
    local host="${1:-}"
    local status_json=""
    local backend_state="unknown"
    local magic_suffix=""
    local corpdns="unknown"
    local resolved=""
    local mode=""
    local target=""
    local fqdn=""

    if [[ -z "$host" ]]; then
      _tailmux_usage
      return 1
    fi

    echo "tailmux doctor"
    echo "  host: $host"

    if ! _tailmux_has_cmd tailscale; then
      echo "  tailscale: not found in PATH"
      return 1
    fi

    status_json="$(_tailmux_status_json || true)"
    if [[ -n "$status_json" ]]; then
      if _tailmux_has_cmd jq; then
        backend_state="$(printf '%s\n' "$status_json" | jq -r '.BackendState // "unknown"' 2>/dev/null)"
      elif _tailmux_has_cmd python3; then
        backend_state="$(printf '%s\n' "$status_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState","unknown"))' 2>/dev/null)"
      fi
      magic_suffix="$(_tailmux_magicdns_suffix_from_json "$status_json" 2>/dev/null || true)"
      magic_suffix="${magic_suffix%.}"
    fi

    if tailscale debug prefs >/dev/null 2>&1; then
      if _tailmux_has_cmd jq; then
        corpdns="$(tailscale debug prefs 2>/dev/null | jq -r '.CorpDNS // "unknown"' 2>/dev/null)"
      elif _tailmux_has_cmd python3; then
        corpdns="$(tailscale debug prefs 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("CorpDNS","unknown"))' 2>/dev/null)"
      fi
    fi

    echo "  tailscale backend: $backend_state"
    echo "  tailscale dns accepted (CorpDNS): $corpdns"
    if [[ -n "$magic_suffix" ]]; then
      echo "  magicdns suffix: $magic_suffix"
    else
      echo "  magicdns suffix: unavailable"
    fi

    resolved="$(_tailmux_resolve_target "$host")"
    target="$(printf '%s' "$resolved" | awk -F '\t' '{print $1}')"
    mode="$(printf '%s' "$resolved" | awk -F '\t' '{print $2}')"
    echo "  tailmux resolution: $host -> $target ($mode)"

    if [[ "$host" != *.* && -n "$magic_suffix" ]]; then
      fqdn="$host.$magic_suffix"
      echo "  tailscale dns query A $fqdn:"
      tailscale dns query "$fqdn" a 2>/dev/null | sed 's/^/    /' || echo "    query failed"
    fi

    if [[ "$mode" == "passthrough" ]]; then
      echo "  recommendation:"
      echo "    - tailmux could not resolve this host via tailnet or system DNS."
      echo "    - verify with: tailscale dns status --all"
      echo "    - if MagicDNS short names fail on macOS OSS CLI, connect using tailnet FQDN or add an alias in \$TAILMUX_HOSTS_FILE."
      echo "    - optional LAN fallback: export TAILMUX_LAN_FALLBACK=1"
    fi
  }

  if [[ -z "${1:-}" ]]; then
    _tailmux_usage
    return 1
  fi

  if [[ "$1" == "doctor" ]]; then
    shift
    _tailmux_doctor "${1:-}"
    return $?
  fi

  local host="$1"
  local resolved
  local target
  local mode

  resolved="$(_tailmux_resolve_target "$host")"
  target="$(printf '%s' "$resolved" | awk -F '\t' '{print $1}')"
  mode="$(printf '%s' "$resolved" | awk -F '\t' '{print $2}')"

  echo "tailmux: resolved $host -> $target ($mode)" >&2
  ssh -t "$target" "PATH=\"/opt/homebrew/bin:/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH\"; if command -v tmux >/dev/null 2>&1; then tmux attach || tmux new; else echo \"tmux not found on remote\" >&2; exit 127; fi"
}
EOF
)"
TAILMUX_BLOCK_BEGIN="# >>> tailmux managed block (tailmux) >>>"
TAILMUX_BLOCK_END="# <<< tailmux managed block (tailmux) <<<"
TAILDRIVE_BLOCK_BEGIN="# >>> tailmux managed block (taildrive) >>>"
TAILDRIVE_BLOCK_END="# <<< tailmux managed block (taildrive) <<<"
