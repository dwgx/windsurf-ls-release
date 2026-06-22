#!/bin/sh
set -eu

CHANNEL="${LS_CHANNEL:-stable}"
TARGET_PATH="${LS_BINARY_PATH:-/opt/windsurf/language_server_linux_x64}"
OWNER="${LS_REPO_OWNER:-dwgx}"
REPO="${LS_REPO_NAME:-windsurf-ls-release}"
RELEASES_BASE_URL="${LS_RELEASES_BASE_URL:-https://github.com/${OWNER}/${REPO}/releases}"
GH_PROXY_PREFIX="${GH_PROXY_PREFIX:-https://ghfast.top/}"
ASSET_NAME="language_server_linux_x64"
CURL_BIN="${CURL_BIN:-curl}"
SHA256SUM_BIN="${SHA256SUM_BIN:-}"

case "$CHANNEL" in
  stable)
    TAG_PREFIX="v"
    ;;
  next)
    TAG_PREFIX="next-v"
    ;;
  *)
    echo "Unsupported LS_CHANNEL: $CHANNEL" >&2
    exit 1
    ;;
esac

log() {
  printf '[update-ls] %s\n' "$*"
}

download_file() {
  url="$1"
  destination="$2"
  "$CURL_BIN" -fsSL "$url" -o "$destination"
}

resolve_sha256_command() {
  if [ -n "$SHA256SUM_BIN" ]; then
    printf '%s\n' "$SHA256SUM_BIN"
    return 0
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s\n' "sha256sum"
    return 0
  fi

  if command -v shasum >/dev/null 2>&1; then
    printf '%s\n' "shasum -a 256"
    return 0
  fi

  if command -v openssl >/dev/null 2>&1; then
    printf '%s\n' "openssl dgst -sha256 -r"
    return 0
  fi

  echo "Could not find a usable sha256 command. Tried: sha256sum, shasum -a 256, openssl dgst -sha256 -r" >&2
  exit 1
}

sha256_file() {
  file_path="$1"
  sha_command="$2"
  if ! command -v "$(printf '%s' "$sha_command" | awk '{print $1}')" >/dev/null 2>&1; then
    echo "Required checksum command is not available: $sha_command" >&2
    exit 1
  fi
  sh -c "$sha_command \"\$1\" | awk '{print \$1}'" _ "$file_path"
}

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT INT TERM

SHA256SUM_BIN="$(resolve_sha256_command)"
log "Using sha256 command: $SHA256SUM_BIN"

releases_html="$tmp_dir/releases.html"
release_page_html="$tmp_dir/release-page.html"
asset_path="$tmp_dir/$ASSET_NAME"

log "Fetching release list for channel $CHANNEL"
download_file "$RELEASES_BASE_URL" "$releases_html"

tag="$(
  python3 - "$releases_html" "$TAG_PREFIX" "$OWNER" "$REPO" <<'PY'
import sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
tag_prefix = sys.argv[2]
owner = sys.argv[3]
repo = sys.argv[4]
needle = f'/{owner}/{repo}/releases/tag/' + tag_prefix
tag_prefix_path = f'/{owner}/{repo}/releases/tag/'
start = 0

while True:
    index = html.find(needle, start)
    if index == -1:
        break
    tag_start = index + len(tag_prefix_path)
    tag_end = html.find('"', tag_start)
    if tag_end == -1:
        break
    tag = html[tag_start:tag_end]
    if tag.startswith(tag_prefix):
        print(tag)
        raise SystemExit(0)
    start = tag_end

raise SystemExit(f"Could not find latest release tag with prefix {tag_prefix!r}")
PY
)"

release_page_url="${RELEASES_BASE_URL}/tag/${tag}"
log "Fetching release notes for $tag"
download_file "$release_page_url" "$release_page_html"

expected_sha256="$(
  python3 - "$release_page_html" <<'PY'
import re
import sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
needle = "linux-x64:"
index = html.find(needle)
if index == -1:
    raise SystemExit("Could not find linux-x64 section in release page")

snippet = html[index:index + 4000]
match = re.search(r'extracted binary:\s*language_server_linux_x64\s*\([^)]*sha256:\s*([0-9a-f]{64})\)', snippet)
if not match:
    raise SystemExit("Could not find sha256 for language_server_linux_x64 in release page")

print(match.group(1))
PY
)"

if [ -f "$TARGET_PATH" ]; then
  log "Comparing local sha256 with remote release"
  current_sha256="$(sha256_file "$TARGET_PATH" "$SHA256SUM_BIN")"
  if [ "$current_sha256" = "$expected_sha256" ]; then
    log "Local file already matches remote sha256; skipping download"
    exit 0
  fi
fi

direct_asset_url="${RELEASES_BASE_URL}/download/${tag}/${ASSET_NAME}"
proxy_asset_url="${GH_PROXY_PREFIX}${direct_asset_url}"

log "Downloading $ASSET_NAME via proxy"
if ! download_file "$proxy_asset_url" "$asset_path"; then
  log "Proxy download failed, falling back to direct GitHub URL"
  download_file "$direct_asset_url" "$asset_path"
fi

log "Verifying sha256"
actual_sha256="$(sha256_file "$asset_path" "$SHA256SUM_BIN")"
if [ "$actual_sha256" != "$expected_sha256" ]; then
  echo "sha256 mismatch: expected $expected_sha256, got $actual_sha256" >&2
  exit 1
fi

chmod 0755 "$asset_path"

target_dir="$(dirname "$TARGET_PATH")"
mkdir -p "$target_dir"
tmp_target="$TARGET_PATH.tmp.$$"
mv "$asset_path" "$tmp_target"
mv -f "$tmp_target" "$TARGET_PATH"

log "Installed $TARGET_PATH from channel $CHANNEL ($tag)"
