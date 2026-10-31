#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output="${1:-$repo_root/lcd-display-analyzer-runtime.tar.gz}"

if [[ "$output" != /* ]]; then
  output="$PWD/$output"
fi

tar \
  --create \
  --gzip \
  --file "$output" \
  --directory "$repo_root" \
  --transform 's,^,lcd-display-analyzer/,' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  README.md \
  run_display_variant_1.sh \
  run_display_variant_2.sh \
  deploy \
  variants

echo "Created $output"
