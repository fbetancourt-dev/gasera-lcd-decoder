#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
missing=0

for command_name in python3 gcc sigrok-cli; do
  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'OK   %-12s %s\n' "$command_name" "$(command -v "$command_name")"
  else
    printf 'MISS %-12s required\n' "$command_name"
    missing=1
  fi
done

for variant in 1 2; do
  variant_dir="$repo_root/variants/display-variant-$variant"
  for file_name in \
    lcd_decoder_light.html \
    lcd_decoder_server.py \
    lcd_decoder_settings.json \
    lcd_decoder_worker.js \
    st7565_trace_export.c \
    calibrations/st7565_digits_16x28.json
  do
    if [[ ! -f "$variant_dir/$file_name" ]]; then
      echo "MISS variant $variant: $file_name"
      missing=1
    fi
  done
done

if (( missing )); then
  echo "Runtime check failed." >&2
  exit 1
fi

temp_dir="$(mktemp -d)"
trap 'rm -rf -- "$temp_dir"' EXIT
for variant in 1 2; do
  gcc -O2 -Wall -Wextra \
    -o "$temp_dir/st7565_variant_$variant" \
    "$repo_root/variants/display-variant-$variant/st7565_trace_export.c"
done
echo "OK   native decoders compiled"

echo
echo "Connected sigrok devices:"
if ! sigrok-cli --scan; then
  echo "No accessible device found. Reconnect USB and verify plugdev/udev access."
fi
