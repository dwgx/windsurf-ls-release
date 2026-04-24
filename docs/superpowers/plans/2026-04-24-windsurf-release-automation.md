# Windsurf Release Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions pipeline that parses the latest stable Windsurf version from the releases HTML, extracts canonical `language_server_*` binaries from archive downloads, and publishes them as GitHub Release assets.

**Architecture:** Keep the repo small: one workflow and three Python 3.12 scripts. The workflow first discovers the newest stable version and uploads a normalized manifest artifact, then a second job downloads canonical archives, extracts binaries, writes a summary, uploads branch-safe artifacts on non-default branches, and publishes a GitHub Release only on the default branch.

**Tech Stack:** GitHub Actions, Python 3.12 standard library, `gh` CLI, `actions/upload-artifact@v4`, `actions/download-artifact@v4`

---

## File Structure

- Create: `.github/workflows/release.yml`
  - Single orchestration workflow for schedule/manual runs, manifest discovery, artifact building, branch-safe validation, and default-branch release publication.
- Create: `scripts/discover_release.py`
  - Fetches `https://windsurf.com/editor/releases`, extracts the `stableReleases` array from HTML, normalizes the latest stable version into `manifest.json`, and writes version metadata to `GITHUB_OUTPUT`.
- Create: `scripts/build_assets.py`
  - Consumes `manifest.json`, downloads canonical archives, extracts `language_server_*`, writes raw assets plus `.gz` variants, and emits a machine-readable `summary.json`.
- Create: `scripts/render_release_notes.py`
  - Converts `summary.json` into deterministic release notes markdown.
- Create: `README.md`
  - Explains repository purpose, published asset names, branch-safe validation flow, and manual workflow commands.

## Implementation Notes

- Validation is workflow-first, not local-test-first, because the user explicitly wants `gh`-driven verification instead of local TDD execution.
- Use Python standard library only. Do not add a package manager or third-party dependencies for parsing or extraction.
- Publish release assets only from the default branch. Feature branches should still run discovery and extraction so `gh` can validate behavior without mutating Releases.
- Treat `linux-x64` as required. If it fails, `build_assets.py` must exit non-zero.

### Task 1: Add Stable Release Discovery

**Files:**
- Create: `scripts/discover_release.py`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the discovery script**

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


RELEASES_URL = "https://windsurf.com/editor/releases"

CANONICAL_TARGETS = [
    {
        "target": "linux-x64",
        "display_name": "Linux x64 (.tar.gz)",
        "archive_type": "tar.gz",
        "expected_binary_name": "language_server_linux_x64",
        "required": True,
    },
    {
        "target": "macos-arm",
        "display_name": "macOS for Apple Silicon (Archive, .zip)",
        "archive_type": "zip",
        "expected_binary_name": "language_server_macos_arm",
        "required": False,
    },
    {
        "target": "macos-x64",
        "display_name": "macOS for Intel (Archive, .zip)",
        "archive_type": "zip",
        "expected_binary_name": "language_server_macos_x64",
        "required": False,
    },
    {
        "target": "windows-arm",
        "display_name": "Windows arm64 (Archive, .zip)",
        "archive_type": "zip",
        "expected_binary_name": "language_server_windows_arm.exe",
        "required": False,
    },
    {
        "target": "windows-x64",
        "display_name": "Windows x64 (Archive, .zip)",
        "archive_type": "zip",
        "expected_binary_name": "language_server_windows_x64.exe",
        "required": False,
    },
]


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "windsurf-release-bot/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def extract_escaped_json_array(html: str, field_name: str) -> list[dict]:
    marker = f'{field_name}\\":'
    start = html.find(marker)
    if start == -1:
        raise ValueError(f"Could not find field {field_name!r} in Windsurf releases HTML.")

    array_start = html.find("[", start)
    if array_start == -1:
        raise ValueError(f"Could not find array start for field {field_name!r}.")

    depth = 0
    in_string = False
    escaped = False

    for index in range(array_start, len(html)):
        char = html[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                raw = html[array_start:index + 1]
                decoded = raw.encode("utf-8").decode("unicode_escape")
                return json.loads(decoded)

    raise ValueError(f"Could not find the closing bracket for field {field_name!r}.")


def build_manifest(stable_releases: list[dict]) -> dict:
    if not stable_releases:
        raise ValueError("The stableReleases array is empty.")

    latest = stable_releases[0]
    version = latest["version"]

    all_entries = []
    for platform_name in ("MacOS", "Windows", "Linux"):
        all_entries.extend(latest.get(platform_name, []))

    by_display_name = {entry["displayName"]: entry for entry in all_entries}
    targets = []

    for canonical_target in CANONICAL_TARGETS:
        entry = by_display_name.get(canonical_target["display_name"])
        if entry is None:
            raise ValueError(
                f"Could not find canonical download entry {canonical_target['display_name']!r} for version {version}."
            )
        targets.append(
            {
                "target": canonical_target["target"],
                "display_name": canonical_target["display_name"],
                "source_url": entry["url"],
                "archive_type": canonical_target["archive_type"],
                "required": canonical_target["required"],
                "expected_binary_name": canonical_target["expected_binary_name"],
            }
        )

    return {
        "version": version,
        "tag": f"v{version}",
        "release_name": f"Windsurf {version}",
        "targets": targets,
    }


def write_github_output(manifest: dict) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"version={manifest['version']}\n")
        handle.write(f"tag={manifest['tag']}\n")
        handle.write(f"release_name={manifest['release_name']}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=RELEASES_URL)
    parser.add_argument("--manifest-out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html = fetch_html(args.url)
    stable_releases = extract_escaped_json_array(html, "stableReleases")
    manifest = build_manifest(stable_releases)

    manifest_path = Path(args.manifest_out)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_github_output(manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add a discovery-only workflow**

```yaml
name: release

on:
  workflow_dispatch:
  schedule:
    - cron: "17 3 * * *"

permissions:
  contents: write

jobs:
  discover:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.discover.outputs.version }}
      tag: ${{ steps.discover.outputs.tag }}
      release_name: ${{ steps.discover.outputs.release_name }}
      skip: ${{ steps.release_check.outputs.skip }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Create manifest directory
        run: mkdir -p "$RUNNER_TEMP/windsurf-release"

      - name: Discover latest stable release
        id: discover
        run: |
          python3 scripts/discover_release.py \
            --manifest-out "$RUNNER_TEMP/windsurf-release/manifest.json"

      - name: Upload manifest artifact
        uses: actions/upload-artifact@v4
        with:
          name: release-manifest
          path: ${{ runner.temp }}/windsurf-release/manifest.json

      - name: Check whether release already exists
        id: release_check
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.discover.outputs.tag }}
        run: |
          if gh release view "$TAG" >/dev/null 2>&1; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
          elif git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Write discovery summary
        run: |
          {
            echo "## Discovery"
            echo "- Version: ${{ steps.discover.outputs.version }}"
            echo "- Tag: ${{ steps.discover.outputs.tag }}"
            echo "- Skip existing release: ${{ steps.release_check.outputs.skip }}"
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 3: Push the branch and run the workflow through `gh`**

Run:

```bash
git push -u origin "$(git branch --show-current)"
gh workflow run release.yml --ref "$(git branch --show-current)"
RUN_ID="$(gh run list --workflow release.yml --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
gh run view "$RUN_ID" --json conclusion --jq '.conclusion'
```

Expected:

- workflow conclusion is `success`
- `discover` job summary shows a concrete Windsurf version and tag
- artifact `release-manifest` is available in the run

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml scripts/discover_release.py
git commit -m "feat: add Windsurf stable release discovery"
```

### Task 2: Add Canonical Asset Extraction

**Files:**
- Create: `scripts/build_assets.py`
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Write the asset builder**

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


CHUNK_SIZE = 1024 * 1024


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "windsurf-release-bot/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)


def extract_archive(archive_path: Path, output_dir: Path, archive_type: str) -> None:
    if archive_type == "zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(output_dir)
        return

    if archive_type == "tar.gz":
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(output_dir)
        return

    raise ValueError(f"Unsupported archive type: {archive_type}")


def find_expected_binary(root: Path, expected_name: str) -> Path:
    matches = [path for path in root.rglob(expected_name) if path.is_file()]
    if not matches:
        raise FileNotFoundError(f"Could not find {expected_name} under {root}")
    if len(matches) > 1:
        raise RuntimeError(f"Found multiple matches for {expected_name}: {matches}")
    return matches[0]


def gzip_copy(source: Path, destination: Path) -> None:
    with source.open("rb") as src_handle, gzip.open(destination, "wb") as dst_handle:
        shutil.copyfileobj(src_handle, dst_handle)


def process_target(target: dict, dist_dir: Path, scratch_root: Path) -> tuple[list[str], str | None]:
    work_dir = scratch_root / target["target"]
    work_dir.mkdir(parents=True, exist_ok=True)

    archive_name = Path(urllib.parse.urlparse(target["source_url"]).path).name
    archive_path = work_dir / archive_name
    extracted_dir = work_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    try:
        download_file(target["source_url"], archive_path)
        extract_archive(archive_path, extracted_dir, target["archive_type"])
        binary_path = find_expected_binary(extracted_dir, target["expected_binary_name"])

        output_path = dist_dir / target["expected_binary_name"]
        shutil.copy2(binary_path, output_path)

        if not output_path.name.endswith(".exe"):
            output_path.chmod(output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        created_assets = [output_path.name]
        gzip_path = output_path.with_name(output_path.name + ".gz")
        try:
            gzip_copy(output_path, gzip_path)
            created_assets.append(gzip_path.name)
        except OSError as exc:
            return created_assets, f"gzip failed: {exc}"

        return created_assets, None
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{target['target']}: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--summary-out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    dist_dir = Path(args.dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "version": manifest["version"],
        "tag": manifest["tag"],
        "release_name": manifest["release_name"],
        "successful_targets": [],
        "failed_targets": [],
    }
    required_failure = False

    with tempfile.TemporaryDirectory(prefix="windsurf-assets-") as temp_dir:
        scratch_root = Path(temp_dir)
        for target in manifest["targets"]:
            try:
                assets, warning = process_target(target, dist_dir, scratch_root)
                entry = {"target": target["target"], "assets": assets}
                if warning:
                    entry["warning"] = warning
                summary["successful_targets"].append(entry)
            except RuntimeError as exc:
                summary["failed_targets"].append(
                    {
                        "target": target["target"],
                        "required": target["required"],
                        "reason": str(exc),
                    }
                )
                if target["required"]:
                    required_failure = True

    Path(args.summary_out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if required_failure:
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Extend the workflow with a branch-safe release job**

```yaml
  release:
    needs: discover
    if: needs.discover.outputs.skip != 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Download manifest artifact
        uses: actions/download-artifact@v4
        with:
          name: release-manifest
          path: ${{ runner.temp }}/windsurf-release

      - name: Build extracted assets
        id: build_assets
        continue-on-error: true
        run: |
          mkdir -p "$RUNNER_TEMP/windsurf-release/dist"
          python3 scripts/build_assets.py \
            --manifest "$RUNNER_TEMP/windsurf-release/manifest.json" \
            --dist-dir "$RUNNER_TEMP/windsurf-release/dist" \
            --summary-out "$RUNNER_TEMP/windsurf-release/summary.json"

      - name: Upload extracted assets artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: windsurf-assets
          path: ${{ runner.temp }}/windsurf-release/dist
          if-no-files-found: ignore

      - name: Upload build summary artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: release-summary
          path: ${{ runner.temp }}/windsurf-release/summary.json
          if-no-files-found: ignore

      - name: Note skipped publication on non-default branches
        if: github.ref != format('refs/heads/{0}', github.event.repository.default_branch)
        run: |
          {
            echo "## Branch validation"
            echo "- Publish steps are skipped on branch $GITHUB_REF_NAME"
            echo "- Download the artifact named windsurf-assets to inspect extracted binaries"
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Fail job when required extraction fails
        if: steps.build_assets.outcome != 'success'
        run: exit 1
```

- [ ] **Step 3: Run the branch workflow again and inspect artifacts**

Run:

```bash
gh workflow run release.yml --ref "$(git branch --show-current)"
RUN_ID="$(gh run list --workflow release.yml --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
gh run download "$RUN_ID" -D /tmp/windsurf-run
find /tmp/windsurf-run -maxdepth 2 -type f | sort
```

Expected:

- workflow conclusion is `success`
- downloaded artifacts include `release-manifest/manifest.json`
- downloaded artifacts include `windsurf-assets/` files such as `language_server_linux_x64`
- logs show the non-default-branch publication note instead of a GitHub Release being created

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml scripts/build_assets.py
git commit -m "feat: add archive extraction for release assets"
```

### Task 3: Add Release Notes Rendering and Default-Branch Publishing

**Files:**
- Create: `scripts/render_release_notes.py`
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Write the release notes renderer**

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def render_notes(summary: dict) -> str:
    lines = [
        f"Extracted language server binaries from Windsurf {summary['version']}.",
        "",
        f"Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Successful targets:",
    ]

    if summary["successful_targets"]:
        for item in summary["successful_targets"]:
            asset_list = ", ".join(item["assets"])
            suffix = f" ({item['warning']})" if "warning" in item else ""
            lines.append(f"- {item['target']}: {asset_list}{suffix}")
    else:
        lines.append("- none")

    lines.extend(["", "Failed or missing targets:"])
    if summary["failed_targets"]:
        for item in summary["failed_targets"]:
            lines.append(f"- {item['target']}: {item['reason']}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "These assets contain extracted language server binaries, not full Windsurf installers.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    Path(args.output).write_text(render_notes(summary), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add release publication steps gated to the default branch**

```yaml
      - name: Render release notes
        if: steps.build_assets.outcome == 'success' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
        run: |
          python3 scripts/render_release_notes.py \
            --summary "$RUNNER_TEMP/windsurf-release/summary.json" \
            --output "$RUNNER_TEMP/windsurf-release/release-notes.md"

      - name: Create draft release
        if: steps.build_assets.outcome == 'success' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ needs.discover.outputs.tag }}
          RELEASE_NAME: ${{ needs.discover.outputs.release_name }}
        run: |
          gh release create "$TAG" \
            --draft \
            --title "$RELEASE_NAME" \
            --notes-file "$RUNNER_TEMP/windsurf-release/release-notes.md"

      - name: Upload release assets
        if: steps.build_assets.outcome == 'success' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ needs.discover.outputs.tag }}
        run: |
          gh release upload "$TAG" "$RUNNER_TEMP/windsurf-release/dist/"* --clobber

      - name: Publish release
        if: steps.build_assets.outcome == 'success' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ needs.discover.outputs.tag }}
        run: |
          gh release edit "$TAG" \
            --draft=false \
            --notes-file "$RUNNER_TEMP/windsurf-release/release-notes.md"
```

- [ ] **Step 3: Verify branch runs still avoid publishing**

Run:

```bash
gh workflow run release.yml --ref "$(git branch --show-current)"
RUN_ID="$(gh run list --workflow release.yml --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
gh run view "$RUN_ID" --log | rg "Create draft release|Upload release assets|Publish release|Branch validation" -n
```

Expected:

- workflow conclusion is `success`
- log output contains the branch validation note
- default-branch-only publish steps are skipped on the feature branch

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml scripts/render_release_notes.py
git commit -m "feat: publish extracted assets on the default branch"
```

### Task 4: Document Repository Usage

**Files:**
- Create: `README.md`

- [ ] **Step 1: Add repository documentation**

````md
# windsurf-linux-server-release

This repository tracks the latest stable Windsurf release from `https://windsurf.com/editor/releases`, extracts canonical `language_server_*` binaries from archive downloads, and publishes them as GitHub Release assets.

## Published assets

- `language_server_linux_x64`
- `language_server_linux_x64.gz`
- `language_server_macos_arm`
- `language_server_macos_arm.gz`
- `language_server_macos_x64`
- `language_server_macos_x64.gz`
- `language_server_windows_arm.exe`
- `language_server_windows_arm.exe.gz`
- `language_server_windows_x64.exe`
- `language_server_windows_x64.exe.gz`

## Workflow triggers

- `schedule`: runs daily
- `workflow_dispatch`: manual runs through the GitHub UI or `gh workflow run`

## Safe validation on branches

Feature-branch runs still parse the latest stable release and build artifacts, but they do not create a GitHub Release. Download the `windsurf-assets` artifact from the run to inspect extracted binaries.

```bash
gh workflow run release.yml --ref "$(git branch --show-current)"
RUN_ID="$(gh run list --workflow release.yml --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
gh run download "$RUN_ID" -D /tmp/windsurf-run
find /tmp/windsurf-run -maxdepth 2 -type f | sort
```

## Publishing from the default branch

After merging to the default branch, trigger the workflow manually or wait for the daily schedule. If the latest stable version already exists as `v<version>`, the workflow exits early. Otherwise it creates a draft release, uploads extracted assets, and publishes the release.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add repository usage guide"
```

### Task 5: Run End-to-End Verification With `gh`

**Files:**
- Modify: none

- [ ] **Step 1: Push the full implementation branch**

Run:

```bash
git push -u origin "$(git branch --show-current)"
```

Expected:

- branch is available on the remote so GitHub Actions can execute the latest workflow definition

- [ ] **Step 2: Verify the branch-safe run**

Run:

```bash
gh workflow run release.yml --ref "$(git branch --show-current)"
RUN_ID="$(gh run list --workflow release.yml --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
gh run view "$RUN_ID" --json conclusion --jq '.conclusion'
gh run download "$RUN_ID" -D /tmp/windsurf-branch-run
find /tmp/windsurf-branch-run -maxdepth 2 -type f | sort
```

Expected:

- workflow conclusion is `success`
- branch run artifacts include `release-manifest` and `windsurf-assets`
- branch logs do not show a created release

- [ ] **Step 3: After merge, verify default-branch publishing**

Run:

```bash
gh workflow run release.yml --ref "$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name')"
RUN_ID="$(gh run list --workflow release.yml --branch "$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name')" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
VERSION="$(gh run download "$RUN_ID" -D /tmp/windsurf-main-run >/dev/null 2>&1 || true; python3 - <<'PY'\nimport json\nfrom pathlib import Path\npath = Path('/tmp/windsurf-main-run/release-manifest/manifest.json')\nprint(json.loads(path.read_text())['version'] if path.exists() else '')\nPY\n)"
gh release view "v${VERSION}"
```

Expected:

- if the version is new, the run creates `Windsurf <version>` and uploads extracted assets
- if the version already exists, the run exits cleanly from the discovery stage with `skip=true`
- in both cases the workflow conclusion is `success`
