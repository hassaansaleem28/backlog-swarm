#!/usr/bin/env bash
# Publish the demo fleet as four GitHub repositories under OWNER (default: the
# account `gh` is signed in as), each named swarm-demo-<name>. Every repository
# pins dependencies with known vulnerabilities on purpose; their READMEs say so.
#
#   scripts/publish_demo.sh [OWNER]
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
owner="${1:-$(gh api user --jq .login)}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

for name in orders-api notify-worker billing-service status-page; do
  repo="$owner/swarm-demo-$name"
  if gh repo view "$repo" >/dev/null 2>&1; then
    echo "$repo exists, skipping"
    continue
  fi
  cp -r "$root/demo/$name" "$work/$name"
  git -C "$work/$name" init -q -b main
  git -C "$work/$name" add -A
  git -C "$work/$name" commit -q -m "Initial commit"
  gh repo create "$repo" --public \
    --description "Backlog Swarm demo fleet: $name (vulnerable dependencies on purpose)" \
    --source "$work/$name" --push
  echo "published https://github.com/$repo"
done
