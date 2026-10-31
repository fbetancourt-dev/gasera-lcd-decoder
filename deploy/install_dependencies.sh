#!/usr/bin/env bash
set -euo pipefail

install_kiosk=false
if [[ "${1:-}" == "--kiosk" ]]; then
  install_kiosk=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--kiosk]" >&2
  exit 2
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer requires a Debian-based system with apt." >&2
  exit 1
fi

sudo_cmd=()
if (( EUID != 0 )); then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "Run this script as root or install sudo." >&2
    exit 1
  fi
  sudo_cmd=(sudo)
fi

packages=(
  python3
  gcc
  sigrok-cli
  sigrok-firmware-fx2lafw
)
if $install_kiosk; then
  packages+=(chromium)
fi

"${sudo_cmd[@]}" apt-get update
"${sudo_cmd[@]}" apt-get install -y "${packages[@]}"

runtime_user="${SUDO_USER:-${USER:-}}"
if [[ -n "$runtime_user" ]] && getent group plugdev >/dev/null 2>&1; then
  "${sudo_cmd[@]}" usermod -aG plugdev "$runtime_user"
  echo "Added $runtime_user to plugdev; log out and back in before capture."
fi

"${sudo_cmd[@]}" udevadm control --reload-rules
"${sudo_cmd[@]}" udevadm trigger

echo "Runtime dependencies installed."
if $install_kiosk; then
  echo "Chromium kiosk support installed."
fi
