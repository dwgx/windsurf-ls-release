# Windsurf Stable Release Automation Design

## Background

This repository will automate publication of extracted Windsurf language server binaries to GitHub Releases.

The source of truth for version discovery is the public Windsurf releases page:

- `https://windsurf.com/editor/releases`

The repository does not follow the upstream Exafunction/Codeium release feed. It follows the latest stable Windsurf version published on the Windsurf website.

## Goals

- Detect the latest stable Windsurf version from the website by parsing HTML.
- Skip all work when the corresponding GitHub Release already exists.
- When a new stable version appears, download platform archives, extract `language_server_*` binaries, always publish the raw binaries, and additionally publish `.gz` variants when compression succeeds.
- Use the Windsurf version as the release identity.
- Make `linux-x64` extraction mandatory for a successful publish.

## Non-Goals

- Publishing original installers or archives as release assets.
- Publishing every historical stable version in one run.
- Tracking `Windsurf Next`.
- Running a local test suite as the primary validation path.
- Supporting installer-only formats such as `.dmg`, `.deb`, or `.exe` when an archive variant already contains the same language server binary.

## Success Criteria

- A scheduled or manual workflow identifies the newest stable version from `https://windsurf.com/editor/releases`.
- If tag `v<version>` already exists, the workflow exits cleanly without creating or mutating a release.
- If tag `v<version>` does not exist, the workflow creates a GitHub Release titled `Windsurf <version>`.
- The release contains extracted language server binaries for the supported canonical targets plus `.gz` variants when compression succeeds.
- `linux-x64` failure causes the workflow to fail and prevents publication.
- Failures on other platforms do not block publication, but they are surfaced in the release notes and workflow summary.

## Design Overview

The system consists of one GitHub Actions workflow and a small Python utility layer.

The workflow has two stages:

1. `discover`
2. `release`

The `discover` stage parses the Windsurf releases page and emits a normalized manifest for the latest stable version. It also checks whether the matching GitHub tag already exists.

The `release` stage consumes the manifest, downloads canonical archive artifacts, extracts `language_server_*` binaries, produces release assets, creates a draft GitHub Release, uploads assets, writes release notes, and publishes the release.

## Source Discovery Strategy

### Version Discovery

The workflow fetches:

- `https://windsurf.com/editor/releases`

The page currently contains server-rendered release data in the returned HTML, including:

- stable release versions
- per-platform download URLs
- per-platform display names

The design intentionally treats this HTML as the only discovery input for stable versions.

### Why Not Use `/download/editor`

The generic editor download page and its redirect API expose useful build metadata, but they are not required for the requested flow.

This repository's contract is:

- first parse the releases page
- then compare against GitHub Releases
- then publish if the version is new

Using the releases page directly keeps the implementation aligned with that contract and avoids depending on a second source for per-version artifact URLs.

## Canonical Platform Targets

Only one archive source is selected per target, even if the page offers multiple installer variants.

### Canonical Targets

- `linux-x64`
- `macos-arm`
- `macos-x64`
- `windows-arm`
- `windows-x64`

### Canonical Source Mapping

- `linux-x64` -> `Linux x64 (.tar.gz)`
- `macos-arm` -> `macOS for Apple Silicon (Archive, .zip)`
- `macos-x64` -> `macOS for Intel (Archive, .zip)`
- `windows-arm` -> `Windows arm64 (Archive, .zip)`
- `windows-x64` -> `Windows x64 (Archive, .zip)`

### Excluded Variants

These are intentionally ignored in the first version:

- `.dmg`
- `.deb`
- Windows user/system installer `.exe`

Reason:

- archive variants already contain the required `language_server_*` binaries
- archive extraction is much more reliable on an Ubuntu GitHub runner
- this avoids platform-specific installer tooling and reduces failure surface

## Manifest Format

The `discover` stage writes `${RUNNER_TEMP}/windsurf-release/manifest.json` and uploads it as a workflow artifact named `release-manifest`.

Example shape:

```json
{
  "version": "2.0.67",
  "tag": "v2.0.67",
  "release_name": "Windsurf 2.0.67",
  "targets": [
    {
      "target": "linux-x64",
      "display_name": "Linux x64 (.tar.gz)",
      "source_url": "https://windsurf-stable.codeiumdata.com/.../Windsurf-linux-x64-2.0.67.tar.gz",
      "archive_type": "tar.gz",
      "required": true,
      "expected_binary_name": "language_server_linux_x64"
    }
  ]
}
```

Fields must be explicit enough that the release stage does not need to know anything about page structure.

## Extraction Strategy

The implementation runs on Ubuntu and performs extraction with Python standard library where practical:

- `zipfile` for `.zip`
- `tarfile` for `.tar.gz`

After extraction, the script recursively searches for a file matching:

- `language_server_*`

The script does not depend on a single absolute path, but known expected paths are:

- Linux: `Windsurf/resources/app/extensions/windsurf/bin/language_server_linux_x64`
- macOS arm: `Windsurf.app/Contents/Resources/app/extensions/windsurf/bin/language_server_macos_arm`
- macOS x64: `Windsurf.app/Contents/Resources/app/extensions/windsurf/bin/language_server_macos_x64`
- Windows arm: `resources/app/extensions/windsurf/bin/language_server_windows_arm.exe`
- Windows x64: `resources/app/extensions/windsurf/bin/language_server_windows_x64.exe`

The search-based extraction makes the workflow tolerant to harmless parent-directory changes while still validating the expected binary name.

## Release Asset Naming

The release assets use the extracted filenames directly and add compressed variants when gzip succeeds.

Expected asset set:

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

For non-Windows binaries, the workflow sets executable permissions before packaging.

If gzip fails for a given binary, the raw binary is still eligible for upload.

## Workflow Structure

### Trigger Modes

The workflow supports:

- `schedule`
- `workflow_dispatch`

The schedule runs once per day at `17 3 * * *` UTC.

### Job 1: `discover`

Responsibilities:

- fetch the releases HTML
- parse stable release data
- select the latest stable version
- build the manifest
- write `${RUNNER_TEMP}/windsurf-release/manifest.json`
- upload artifact `release-manifest`
- check whether tag `v<version>` already exists
- emit:
  - `skip=true|false`
  - version metadata
  - manifest artifact availability

Failure behavior:

- if the page cannot be parsed, fail the workflow
- if no stable version is found, fail the workflow

### Job 2: `release`

Runs only when `skip=false`.

Responsibilities:

- download artifact `release-manifest`
- create a working directory
- download canonical archives
- extract language server binaries
- place final assets in `dist/`
- write a machine-readable summary
- create a draft GitHub Release
- upload assets
- publish the release

The initial implementation should process targets sequentially inside one Ubuntu job. Matrix fan-out is unnecessary for the first version because all chosen source formats are extractable on Linux.

## Release Creation Rules

### Tag and Release Identity

- tag: `v<version>`
- title: `Windsurf <version>`

Examples:

- tag: `v2.0.67`
- title: `Windsurf 2.0.67`

### Skip Rule

If the repository already has a release or tag matching `v<version>`, the workflow exits without creating or modifying assets.

The existence check must happen before any large downloads.

### Draft-Then-Publish

The release stage first creates a draft release, uploads all available assets, then publishes it.

Reason:

- avoids partially visible releases
- keeps failure behavior easier to reason about

## Failure Handling

### Hard Failure

`linux-x64` is mandatory.

If `linux-x64` fails at any of these steps, the workflow fails and no release is published:

- source URL missing from manifest
- download failure
- extraction failure
- binary not found
- upload failure

### Soft Failure

These targets are best-effort:

- `macos-arm`
- `macos-x64`
- `windows-arm`
- `windows-x64`

If one of them fails:

- continue processing remaining targets
- do not block release publication
- record the failure reason in the workflow summary
- include the failure in release notes

### Compression Failure

If `.gz` creation fails but the raw binary exists:

- upload the raw binary
- mark gzip as unavailable for that target
- do not fail the target solely because of gzip

## Release Notes Format

Release notes should be generated from the extraction summary and include:

- source version
- publication timestamp
- successful targets
- missing or failed targets
- a note that assets are extracted language server binaries, not full installers

Example outline:

```md
Extracted language server binaries from Windsurf 2.0.67.

Successful targets:
- linux-x64
- macos-arm
- macos-x64

Failed or missing targets:
- windows-arm: binary not found in archive
- windows-x64: download failed
```

## Repository Layout

Proposed initial layout:

```text
.github/workflows/release.yml
scripts/discover_release.py
scripts/build_assets.py
scripts/render_release_notes.py
```

Optional small helper modules may be added under `scripts/` if needed, but the first version should keep file count low.

## Data Flow

1. Workflow starts from `schedule` or `workflow_dispatch`.
2. `discover_release.py` fetches the Windsurf releases page.
3. It extracts the latest stable version and canonical target URLs.
4. It writes `${RUNNER_TEMP}/windsurf-release/manifest.json` and uploads artifact `release-manifest`.
5. It checks for existing tag `v<version>`.
6. If the tag exists, workflow stops successfully.
7. If the tag does not exist, the `release` job downloads artifact `release-manifest`.
8. `build_assets.py` downloads canonical archives.
9. The script extracts and copies `language_server_*` binaries into `dist/`.
10. The script generates `.gz` companions where possible.
11. The workflow creates a draft GitHub Release.
12. Assets are uploaded.
13. Release notes are rendered from the summary.
14. The draft release is published.

## Security and Operational Considerations

- Use `GITHUB_TOKEN` with the minimum permissions needed for creating releases and uploading assets.
- Do not execute extracted binaries during the workflow.
- Do not rely on desktop installers or GUI tools.
- Keep downloads in temporary directories and clean them up at job end.
- Prefer explicit timeouts on network operations to avoid hanging runs.

## Validation Plan

The primary validation path is GitHub Actions plus `gh`, not a local TDD test suite.

### Pre-Publish Validation

Use manual runs to validate:

- latest stable version parsing
- skip behavior when tag already exists
- asset extraction for all canonical targets
- mandatory failure behavior for `linux-x64`

### Operational Validation Commands

Examples:

```bash
gh workflow run release.yml
gh run list --workflow release.yml
gh run watch <run-id>
gh run view <run-id> --log-failed
gh release view v2.0.67
gh release download v2.0.67
```

### What To Check In Early Runs

- the discovered version matches the latest stable entry on the website
- the workflow skips before downloading large archives when the tag exists
- release notes reflect the actual extraction results
- uploaded filenames match the extracted binaries and `.gz` variants

## Future Extensions

These are intentionally deferred:

- supporting `Windsurf Next`
- backfilling older stable releases
- publishing checksums
- matrix parallelization
- retry policies per platform
- richer HTML parsing fallback logic

## Recommendation

Implement the first version with:

- one GitHub Actions workflow
- Python 3.12 scripts
- releases-page HTML as the single discovery source
- canonical archive-only platform selection
- sequential extraction on Ubuntu
- mandatory `linux-x64` and best-effort other targets

This yields the smallest reliable system that matches the repository goal and minimizes avoidable platform-specific complexity.
