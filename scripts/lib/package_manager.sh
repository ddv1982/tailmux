# shellcheck shell=bash
# Shared package manager primitives

detect_package_manager() {
  if command_exists brew; then
    echo "brew"
    return 0
  fi
  if command_exists apt-get; then
    echo "apt-get"
    return 0
  fi
  if command_exists dnf; then
    echo "dnf"
    return 0
  fi
  if command_exists yum; then
    echo "yum"
    return 0
  fi
  if command_exists pacman; then
    echo "pacman"
    return 0
  fi
  echo "none"
}

detect_linux_package_manager() {
  if command_exists apt-get; then
    echo "apt-get"
    return 0
  fi
  if command_exists dnf; then
    echo "dnf"
    return 0
  fi
  if command_exists yum; then
    echo "yum"
    return 0
  fi
  if command_exists pacman; then
    echo "pacman"
    return 0
  fi
  echo "none"
}

package_manager_install() {
  local package="${1:?missing package name}"
  local pm
  pm="$(detect_package_manager)"

  case "$pm" in
    brew)
      brew install "$package"
      ;;
    apt-get)
      sudo apt-get update -y && sudo apt-get install -y "$package"
      ;;
    dnf)
      sudo dnf install -y "$package"
      ;;
    yum)
      sudo yum install -y "$package"
      ;;
    pacman)
      sudo pacman -S --noconfirm "$package"
      ;;
    *)
      return 1
      ;;
  esac
}

package_manager_uninstall() {
  local package="${1:?missing package name}"
  local purge="${2:-false}"
  local pm
  pm="$(detect_package_manager)"

  case "$pm" in
    brew)
      HOMEBREW_NO_AUTOREMOVE=1 brew uninstall "$package"
      ;;
    apt-get)
      sudo apt-get remove -y "$package"
      if [[ "$purge" == "true" ]]; then
        sudo apt-get purge -y "$package" 2>/dev/null || true
      fi
      ;;
    dnf)
      sudo dnf remove -y "$package"
      ;;
    yum)
      sudo yum remove -y "$package"
      ;;
    pacman)
      sudo pacman -R --noconfirm "$package"
      ;;
    *)
      return 1
      ;;
  esac
}

package_manager_install_hint() {
  local package="${1:?missing package name}"
  local pm
  pm="$(detect_package_manager)"

  case "$pm" in
    brew)
      echo "Install manually with: brew install $package"
      ;;
    apt-get)
      echo "Install manually with: sudo apt-get update -y && sudo apt-get install -y $package"
      ;;
    dnf)
      echo "Install manually with: sudo dnf install -y $package"
      ;;
    yum)
      echo "Install manually with: sudo yum install -y $package"
      ;;
    pacman)
      echo "Install manually with: sudo pacman -S --noconfirm $package"
      ;;
    *)
      echo "Install $package manually using your distribution's package manager."
      ;;
  esac
}

linux_package_manager_install() {
  local package="${1:?missing package name}"
  local pm
  pm="$(detect_linux_package_manager)"

  case "$pm" in
    apt-get)
      sudo apt-get update -y && sudo apt-get install -y "$package"
      ;;
    dnf)
      sudo dnf install -y "$package"
      ;;
    yum)
      sudo yum install -y "$package"
      ;;
    pacman)
      sudo pacman -S --noconfirm "$package"
      ;;
    *)
      return 1
      ;;
  esac
}

linux_package_manager_uninstall() {
  local package="${1:?missing package name}"
  local purge="${2:-false}"
  local pm
  pm="$(detect_linux_package_manager)"

  case "$pm" in
    apt-get)
      sudo apt-get remove -y "$package"
      if [[ "$purge" == "true" ]]; then
        sudo apt-get purge -y "$package" 2>/dev/null || true
      fi
      ;;
    dnf)
      sudo dnf remove -y "$package"
      ;;
    yum)
      sudo yum remove -y "$package"
      ;;
    pacman)
      sudo pacman -R --noconfirm "$package"
      ;;
    *)
      return 1
      ;;
  esac
}

linux_package_manager_install_hint() {
  local package="${1:?missing package name}"
  local pm
  pm="$(detect_linux_package_manager)"

  case "$pm" in
    apt-get)
      echo "Install manually with: sudo apt-get update -y && sudo apt-get install -y $package"
      ;;
    dnf)
      echo "Install manually with: sudo dnf install -y $package"
      ;;
    yum)
      echo "Install manually with: sudo yum install -y $package"
      ;;
    pacman)
      echo "Install manually with: sudo pacman -S --noconfirm $package"
      ;;
    *)
      echo "Install $package manually using your distribution's package manager."
      ;;
  esac
}
