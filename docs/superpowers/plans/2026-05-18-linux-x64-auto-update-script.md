# Linux x64 Auto-Update Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bash script that downloads the latest Windsurf `language_server_linux_x64` binary into a local path, defaulting to `stable` and allowing path/channel overrides through environment variables.

**Architecture:** A single `tools/update_ls_linux_x64.sh` script will call the GitHub Releases API with `curl`, resolve the latest release asset for the selected channel, download to a temporary file, then atomically replace the target binary. The script will only depend on POSIX shell utilities plus `curl`, `python3`, and `mktemp`, so it can run on machines without `gh`.

**Tech Stack:** `sh`, `curl`, `python3`, GitHub Releases API

---

### Task 1: Add the update script

**Files:**
- Create: `tools/update_ls_linux_x64.sh`

- [ ] **Step 1: Write the script**

```sh
#!/bin/sh
set -eu

CHANNEL="${LS_CHANNEL:-stable}"
TARGET_PATH="${LS_BINARY_PATH:-/opt/windsurf/language_server_linux_x64}"
OWNER="CaiJingLong"
REPO="windsurf-linux-server-release"
API_URL="https://api.github.com/repos/${OWNER}/${REPO}/releases"

case "$CHANNEL" in
  stable)
    TAG_PREFIX=""
    ;;
  next)
    TAG_PREFIX="next-"
    ;;
  *)
    echo "Unsupported LS_CHANNEL: $CHANNEL" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT INT TERM

release_json="$tmp_dir/releases.json"
asset_path="$tmp_dir/language_server_linux_x64"

curl -fsSL "$API_URL" -o "$release_json"

asset_url="$(
  python3 - "$release_json" "$CHANNEL" "$TAG_PREFIX" <<'PY'
import json
import sys
from pathlib import Path

releases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
channel = sys.argv[2]
tag_prefix = sys.argv[3]

for release in releases:
    tag_name = release.get("tag_name", "")
    if not tag_name.startswith(f"{tag_prefix}v"):
        continue
    for asset in release.get("assets", []):
        if asset.get("name") == "language_server_linux_x64":
            print(asset["browser_download_url"])
            raise SystemExit(0)

raise SystemExit(f"Could not find language_server_linux_x64 for channel {channel}")
PY
)"

curl -fsSL "$asset_url" -o "$asset_path"
chmod 0755 "$asset_path"

target_dir="$(dirname "$TARGET_PATH")"
mkdir -p "$target_dir"
tmp_target="$TARGET_PATH.tmp.$$"
mv "$asset_path" "$tmp_target"
mv -f "$tmp_target" "$TARGET_PATH"

echo "Updated $TARGET_PATH from channel $CHANNEL"
```

- [ ] **Step 2: Verify the script syntax**

Run: `sh -n tools/update_ls_linux_x64.sh`
Expected: exit 0

- [ ] **Step 3: Make the script executable**

Run: `chmod +x tools/update_ls_linux_x64.sh`
Expected: file mode includes execute bit

### Task 2: Document usage

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short usage section**

```md
## Local Linux x64 updater

```bash
LS_CHANNEL=stable ./tools/update_ls_linux_x64.sh
LS_BINARY_PATH=/tmp/language_server_linux_x64 LS_CHANNEL=next ./tools/update_ls_linux_x64.sh
```
```

- [ ] **Step 2: Keep the docs minimal and aligned with the script defaults**

Run: `sed -n '1,220p' README.md`
Expected: the new section explains the default target path and `LS_CHANNEL`

### Task 3: Verify behavior locally

**Files:**
- Test: `tools/update_ls_linux_x64.sh`

- [ ] **Step 1: Run a dry syntax check**

Run: `sh -n tools/update_ls_linux_x64.sh`
Expected: no output, exit 0

- [ ] **Step 2: Verify the script resolves a release asset**

Run: `LS_BINARY_PATH=/tmp/language_server_linux_x64 LS_CHANNEL=stable ./tools/update_ls_linux_x64.sh`
Expected: script prints `Updated /tmp/language_server_linux_x64 from channel stable`

- [ ] **Step 3: Confirm the downloaded file exists and is executable**

Run: `test -x /tmp/language_server_linux_x64 && file /tmp/language_server_linux_x64`
Expected: executable ELF binary

- [ ] **Step 4: Commit**

```bash
git add tools/update_ls_linux_x64.sh README.md docs/superpowers/plans/2026-05-18-linux-x64-auto-update-script.md
git commit -m "feat: add linux x64 auto update script"
```
