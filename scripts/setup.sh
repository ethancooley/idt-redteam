#!/usr/bin/env bash
# Fetch the system under attack at a pinned commit and install both packages.
#   ./scripts/setup.sh            (run from the repo root, inside your virtualenv)
set -euo pipefail
UPSTREAM_URL="https://github.com/ethancooley/idt-prep-copilot"
UPSTREAM_COMMIT="47a7ba6926321f45201aeec5b2f9065069f21db8"
DIR="vendor/idt-prep-copilot"

if [ ! -d "$DIR/.git" ]; then
  git clone --quiet "$UPSTREAM_URL" "$DIR"
fi
git -C "$DIR" fetch --quiet origin "$UPSTREAM_COMMIT" 2>/dev/null || git -C "$DIR" fetch --quiet origin
git -C "$DIR" -c advice.detachedHead=false checkout --quiet "$UPSTREAM_COMMIT"
pip install --quiet -e "$DIR" -e ".[dev]"
echo "IDT Prep Copilot pinned at ${UPSTREAM_COMMIT:0:7}; idt-redteam installed."
