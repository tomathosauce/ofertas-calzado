#!/usr/bin/env bash
# Install GitHub CLI on Debian/Ubuntu and configure this user's Git credentials.
set -euo pipefail
trap 'printf "Setup failed at line %s. See the error above, then rerun ./setup-github.sh.\n" "$LINENO" >&2' ERR

if [[ $EUID -eq 0 ]]; then
  echo 'Run this script as your normal user, without sudo.' >&2
  echo 'It will request sudo only for the installation steps.' >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo 'This installer requires Debian or Ubuntu (apt-get).' >&2
    exit 1
  fi

  echo 'Installing GitHub CLI from the official GitHub package repository…'
  if ! command -v curl >/dev/null 2>&1 || \
    [[ $(dpkg-query -W -f='${Status}' ca-certificates 2>/dev/null || true) != 'install ok installed' ]]; then
    if ! sudo apt-get update; then
      echo 'Some package indexes could not refresh; trying prerequisite installation with available indexes.' >&2
    fi
    sudo apt-get install -y curl ca-certificates
  fi

  key_file=$(mktemp)
  trap 'rm -f -- "$key_file"' EXIT
  curl --fail --silent --show-error --location \
    https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    --output "$key_file"
  sudo install -d -m 755 /etc/apt/keyrings /etc/apt/sources.list.d
  sudo install -m 644 "$key_file" /etc/apt/keyrings/githubcli-archive-keyring.gpg

  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' \
    "$(dpkg --print-architecture)" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null

  # Refresh only GitHub's repository: unrelated broken sources must not block gh.
  sudo apt-get update \
    -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/github-cli.list \
    -o Dir::Etc::sourceparts=- \
    -o APT::Get::List-Cleanup=0
  sudo apt-get install -y gh
else
  echo 'GitHub CLI is already installed.'
fi

gh --version
if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  echo 'Follow the browser login instructions and authorize your GitHub account.'
  gh auth login --hostname github.com --git-protocol https --web
fi
gh auth setup-git --hostname github.com
gh auth status --hostname github.com

echo
echo 'GitHub authentication is configured for your user.'
echo 'This script does not push commits or enable scheduled publishing.'
