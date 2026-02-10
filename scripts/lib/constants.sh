# shellcheck shell=bash
# shellcheck disable=SC2034
# Shared constants
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TAILMUX_FUNC='tailmux() { if [[ -z "${1:-}" ]]; then echo "Usage: tailmux <host>" >&2; return 1; fi; local host="$1"; local ip=""; while read -r addr name rest; do [[ "$name" == "$host" ]] && ip="$addr" && break; done < <(tailscale status 2>/dev/null); if [[ -z "$ip" ]]; then ip="$host"; fi; ssh -t "$ip" "PATH=\"/opt/homebrew/bin:/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH\"; if command -v tmux >/dev/null 2>&1; then tmux attach || tmux new; else echo \"tmux not found on remote\" >&2; exit 127; fi"; }'
TAILMUX_BLOCK_BEGIN="# >>> tailmux managed block (tailmux) >>>"
TAILMUX_BLOCK_END="# <<< tailmux managed block (tailmux) <<<"
TAILDRIVE_BLOCK_BEGIN="# >>> tailmux managed block (taildrive) >>>"
TAILDRIVE_BLOCK_END="# <<< tailmux managed block (taildrive) <<<"
