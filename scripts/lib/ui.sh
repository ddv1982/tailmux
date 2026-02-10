# shellcheck shell=bash
print_step() { printf "\n%b→%b %s\n" "$GREEN" "$NC" "$1"; }
print_success() { printf "%b✓%b %s\n" "$GREEN" "$NC" "$1"; }
print_warning() { printf "%b⚠%b %s\n" "$YELLOW" "$NC" "$1"; }
print_error() { printf "%b✗%b %s\n" "$RED" "$NC" "$1" >&2; }

confirm() {
  local prompt=$1 default=${2:-n}
  local reply
  read -r -p "$prompt " reply
  reply=${reply:-$default}
  [[ "$reply" =~ ^[Yy]$ ]]
}
