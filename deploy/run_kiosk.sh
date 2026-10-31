#!/usr/bin/env bash
set -euo pipefail

variant="${1:-2}"
if [[ "$variant" != "1" && "$variant" != "2" ]]; then
  echo "Usage: $0 [1|2]" >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
port=8081

browser=""
for candidate in firefox-esr chromium chromium-browser firefox; do
  if command -v "$candidate" >/dev/null 2>&1; then
    browser="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$browser" ]]; then
  echo "Browser (firefox-esr or chromium) is required." >&2
  exit 1
fi

python3 "$repo_root/lcd_decoder_server.py" --host 0.0.0.0 --port "$port" --variant "v${variant}" &
server_pid=$!

cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

url="http://127.0.0.1:${port}/lcd_decoder_light.html?variant=${variant}"
for _ in {1..50}; do
  if python3 -c \
    "import urllib.request; urllib.request.urlopen('$url', timeout=.2).close()" \
    >/dev/null 2>&1
  then
    break
  fi
  sleep .1
done

profile_dir="${XDG_CACHE_HOME:-$HOME/.cache}/gasera-lcd-decoder-kiosk"
if [[ "$browser" == *"firefox"* ]]; then
  "$browser" --kiosk "$url"
else
  "$browser" \
    --kiosk \
    --start-maximized \
    --no-first-run \
    --noerrdialogs \
    --disable-session-crashed-bubble \
    --user-data-dir="$profile_dir" \
    "$url"
fi
