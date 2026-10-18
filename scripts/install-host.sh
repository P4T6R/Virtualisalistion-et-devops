#!/usr/bin/env bash
# Operator-run installation on the Ubuntu/Pop!_OS host, not inside a project guest.
set -euo pipefail
. /etc/os-release
codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
if [[ "$codename" != "noble" ]]; then
  echo 'This installer targets Ubuntu/Pop!_OS 24.04 (noble). Review the official installer for other systems.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y curl gnupg ca-certificates ruby python3 apache2-utils
if ! command -v vagrant >/dev/null 2>&1; then
  temp_dir="$(mktemp -d)"
  curl -fsSL https://apt.releases.hashicorp.com/gpg -o "$temp_dir/hashicorp.asc"
  gpg --batch --dearmor --output "$temp_dir/hashicorp.gpg" "$temp_dir/hashicorp.asc"
  sudo install -m 644 "$temp_dir/hashicorp.gpg" /usr/share/keyrings/hashicorp-archive-keyring.gpg
  printf 'deb [arch=%s signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com %s main\n' \
    "$(dpkg --print-architecture)" "$codename" > "$temp_dir/hashicorp.list"
  sudo install -m 644 "$temp_dir/hashicorp.list" /etc/apt/sources.list.d/hashicorp.list
  sudo apt-get update
  sudo apt-get install -y vagrant
  printf 'Repository setup files retained for inspection: %s\n' "$temp_dir"
fi
vagrant --version
VBoxManage --version
