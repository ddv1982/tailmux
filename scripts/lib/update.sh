# shellcheck shell=bash
# Update detection and upgrade logic for managed packages

_update_index_refreshed=false

_is_package_installed() {
  local package="${1:?missing package}"
  case "$package" in
    tailscale) command_exists tailscale ;;
    tmux) command_exists tmux ;;
    davfs2) davfs2_installed ;;
    *) return 1 ;;
  esac
}

get_installed_version() {
  local package="${1:?missing package}"
  case "$package" in
    tailscale)
      tailscale version 2>/dev/null | head -n1 | tr -d '[:space:]'
      ;;
    tmux)
      tmux -V 2>/dev/null | sed 's/^tmux[[:space:]]*//'
      ;;
    davfs2)
      mount.davfs --version 2>&1 | head -n1 | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -n1
      ;;
  esac
}

_refresh_package_index() {
  local os_name="${1:?missing os name}"
  if [[ "$_update_index_refreshed" == true ]]; then
    return 0
  fi
  print_step "Refreshing package index"
  if [[ "$os_name" == "Darwin" ]]; then
    if command_exists brew; then
      brew update --quiet 2>/dev/null || true
    fi
  else
    if command_exists apt-get; then
      sudo apt-get update -y -qq 2>/dev/null || true
    fi
  fi
  _update_index_refreshed=true
}

# Echoes the available version if outdated.
# Returns: 0=outdated, 1=up-to-date, 2=can't check
check_package_outdated() {
  local package="${1:?missing package}"
  local os_name
  os_name="$(get_os_name)"

  if [[ "$os_name" == "Darwin" ]]; then
    _check_brew_outdated "$package"
    return $?
  fi

  case "$package" in
    tailscale) _check_linux_tailscale_outdated ;;
    *) _check_linux_pm_outdated "$package" ;;
  esac
}

_check_brew_outdated() {
  local package="${1:?missing package}"
  local outdated_output
  if ! command_exists brew; then
    return 2
  fi
  outdated_output="$(HOMEBREW_NO_AUTO_UPDATE=1 brew outdated --formula --quiet 2>/dev/null)" || return 2
  if printf '%s\n' "$outdated_output" | grep -qx "$package"; then
    # Get the available version from brew info
    local avail
    avail="$(brew info --formula --json=v2 "$package" 2>/dev/null \
      | grep -o '"stable":{[^}]*"version":"[^"]*"' \
      | head -n1 | grep -oE '"version":"[^"]*"' | sed 's/"version":"//;s/"//' || true)"
    if [[ -n "$avail" ]]; then
      echo "$avail"
    fi
    return 0
  fi
  return 1
}

_check_linux_tailscale_outdated() {
  local upstream_version
  # tailscale version --upstream prints the latest available version (added in recent versions)
  upstream_version="$(tailscale version --upstream 2>/dev/null | head -n1 | tr -d '[:space:]' || true)"
  if [[ -z "$upstream_version" ]]; then
    return 2
  fi
  local installed_version
  installed_version="$(get_installed_version tailscale)"
  if [[ -z "$installed_version" ]]; then
    return 2
  fi
  if [[ "$installed_version" == "$upstream_version" ]]; then
    return 1
  fi
  echo "$upstream_version"
  return 0
}

_check_linux_pm_outdated() {
  local package="${1:?missing package}"
  local pm
  pm="$(detect_linux_package_manager)"
  case "$pm" in
    apt-get)
      local apt_output
      apt_output="$(apt list --upgradable 2>/dev/null | grep "^${package}/" || true)"
      if [[ -n "$apt_output" ]]; then
        local avail
        avail="$(printf '%s' "$apt_output" | grep -oE '[0-9]+\.[0-9]+[.0-9a-z~+-]*' | head -n1 || true)"
        [[ -n "$avail" ]] && echo "$avail"
        return 0
      fi
      return 1
      ;;
    dnf)
      # dnf check-update exits 100 when updates are available, 0 when up to date
      local dnf_output dnf_line
      dnf_output="$(dnf check-update "$package" 2>/dev/null)" || true
      dnf_line="$(printf '%s\n' "$dnf_output" | grep "^${package}" || true)"
      if [[ -n "$dnf_line" ]]; then
        local _pkg avail _repo
        read -r _pkg avail _repo <<< "$dnf_line"
        [[ -n "$avail" ]] && echo "$avail"
        return 0
      fi
      return 1
      ;;
    yum)
      # yum check-update exits 100 when updates are available, 0 when up to date
      local yum_output yum_line
      yum_output="$(yum check-update "$package" 2>/dev/null)" || true
      yum_line="$(printf '%s\n' "$yum_output" | grep "^${package}" || true)"
      if [[ -n "$yum_line" ]]; then
        local _pkg avail _repo
        read -r _pkg avail _repo <<< "$yum_line"
        [[ -n "$avail" ]] && echo "$avail"
        return 0
      fi
      return 1
      ;;
    pacman)
      # pacman -Qu format: "package old_version -> new_version"
      local pacman_output pacman_line
      pacman_output="$(pacman -Qu 2>/dev/null)" || true
      pacman_line="$(printf '%s\n' "$pacman_output" | grep "^${package} " || true)"
      if [[ -n "$pacman_line" ]]; then
        local _pkg _old _arrow avail
        read -r _pkg _old _arrow avail <<< "$pacman_line"
        [[ -n "$avail" ]] && echo "$avail"
        return 0
      fi
      return 1
      ;;
    *)
      return 2
      ;;
  esac
}

upgrade_package() {
  local package="${1:?missing package}"
  local os_name
  os_name="$(get_os_name)"

  if [[ "$os_name" == "Darwin" ]]; then
    _upgrade_brew_package "$package"
    return $?
  fi

  case "$package" in
    tailscale) _upgrade_linux_tailscale ;;
    *) _upgrade_linux_pm_package "$package" ;;
  esac
}

_upgrade_brew_package() {
  local package="${1:?missing package}"
  local upgrade_output
  if ! command_exists brew; then
    return 1
  fi
  if ! upgrade_output="$(brew upgrade "$package" 2>&1)"; then
    if [[ -n "$upgrade_output" ]]; then
      print_warning "brew: $(printf '%s\n' "$upgrade_output" | head -n1)"
    fi
    return 1
  fi
  if [[ "$package" == "tailscale" ]]; then
    print_step "Restarting Tailscale daemon"
    local brew_bin
    brew_bin="$(command -v brew)"
    sudo "$brew_bin" services restart tailscale >/dev/null 2>&1 || true
  fi
  return 0
}

_upgrade_linux_tailscale() {
  local tailscale_track="${TAILMUX_TAILSCALE_TRACK:-stable}"
  if ! command_exists curl; then
    print_error "curl is required to upgrade Tailscale"
    return 1
  fi
  if curl -fsSL https://tailscale.com/install.sh | TRACK="$tailscale_track" sh; then
    return 0
  fi
  return 1
}

_upgrade_linux_pm_package() {
  local package="${1:?missing package}"
  local pm
  pm="$(detect_linux_package_manager)"
  case "$pm" in
    apt-get)  sudo apt-get install -y --only-upgrade "$package" ;;
    dnf)      sudo dnf upgrade -y "$package" ;;
    yum)      sudo yum update -y "$package" ;;
    pacman)   sudo pacman -S --noconfirm "$package" ;;
    *)        return 1 ;;
  esac
}

do_update() {
  echo ""
  echo "tailmux update"
  echo "=============="
  echo ""

  local os_name
  os_name="$(get_os_name)"

  _refresh_package_index "$os_name"

  local -a outdated_packages=()
  local -a outdated_versions=()
  local -a checked_packages=()
  local package installed_version available_version
  local check_status

  for package in "${TAILMUX_MANAGED_PACKAGES[@]}"; do
    if ! _is_package_installed "$package"; then
      continue
    fi
    checked_packages+=("$package")
    installed_version="$(get_installed_version "$package")"

    set +e
    available_version="$(check_package_outdated "$package")"
    check_status=$?
    set -e

    case $check_status in
      0)
        outdated_packages+=("$package")
        outdated_versions+=("$available_version")
        print_warning "$package ${installed_version:-?} -> ${available_version:-newer version available}"
        ;;
      1)
        print_success "$package ${installed_version:-?} is up to date"
        ;;
      2)
        print_warning "$package ${installed_version:-?} (could not check for updates)"
        ;;
    esac
  done

  if [[ ${#checked_packages[@]} -eq 0 ]]; then
    print_warning "No managed packages are installed"
    return 0
  fi

  if [[ ${#outdated_packages[@]} -eq 0 ]]; then
    echo ""
    print_success "All packages are up to date"
    return 0
  fi

  echo ""
  echo "Packages to upgrade:"
  local i
  for i in "${!outdated_packages[@]}"; do
    echo "  - ${outdated_packages[$i]}${outdated_versions[$i]:+ -> ${outdated_versions[$i]}}"
  done
  echo ""

  if ! confirm "Upgrade all? [Y/n]" "y"; then
    echo "Update cancelled."
    return 0
  fi

  local failures=0
  for package in "${outdated_packages[@]}"; do
    print_step "Upgrading $package"
    if upgrade_package "$package"; then
      print_success "$package upgraded"
    else
      print_error "Failed to upgrade $package"
      ((++failures))
    fi
  done

  echo ""
  if [[ $failures -eq 0 ]]; then
    print_success "All packages upgraded successfully"
  else
    print_warning "$failures package(s) failed to upgrade"
    return 1
  fi
}

_hint_available_updates() {
  local package available_version check_status
  local has_updates=false

  for package in "${TAILMUX_MANAGED_PACKAGES[@]}"; do
    if ! _is_package_installed "$package"; then
      continue
    fi
    set +e
    available_version="$(check_package_outdated "$package")"
    check_status=$?
    set -e
    if [[ $check_status -eq 0 ]]; then
      has_updates=true
      break
    fi
  done

  if [[ "$has_updates" == true ]]; then
    echo ""
    print_warning "Some packages have updates available. Run 'setup.sh update' to upgrade."
  fi
}
