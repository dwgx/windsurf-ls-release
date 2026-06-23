# windsurf-ls-release

Maintained release mirror for extracted Windsurf / Devin Desktop `language_server_*`
binaries used by WindsurfAPI.

This is the public binary source used by WindsurfAPI's `install-ls.sh` fallback.
The user-facing path stays simple:

```bash
bash install-ls.sh
```

When WindsurfAPI itself does not publish a matching language server asset, the
installer downloads from:

```text
https://github.com/dwgx/windsurf-ls-release/releases/latest/download
```

This repository tracks the latest stable and next Devin Desktop releases from
`https://docs.devin.ai/desktop/releases` and
`https://docs.devin.ai/desktop/releases-next`, extracts canonical
`language_server_*` binaries from archive downloads, and publishes them as
GitHub Release assets.

Stable releases are normal releases and may be marked as GitHub's Latest
release. Next-channel releases are prereleases and are explicitly published with
`--latest=false`, so `/releases/latest/download/...` remains stable-only.

## Trust and risk model

This repository publishes extracted binaries, not source-built artifacts. Treat
the assets as redistributed upstream binaries from Devin Desktop/Windsurf
packages. Each release records:

- source release page and channel
- upstream package name and product version
- extracted asset name
- size and SHA256 for each binary and gzip asset
- machine-readable release metadata and checksum files
- extraction failures, if any

The CI fails closed if release discovery or extraction shape changes. Operators
who need a private mirror can keep using WindsurfAPI's `WINDSURFAPI_LS_RELEASE`
override.

## WindsurfAPI integration

WindsurfAPI now defaults its desktop-extracted LS fallback to this repository:

```bash
WINDSURFAPI_LS_RELEASE=https://github.com/dwgx/windsurf-ls-release/releases/latest/download bash install-ls.sh
```

The environment variable is optional because current WindsurfAPI releases set
that URL as the default fallback. It remains useful for private mirrors, pinned
release URLs, or emergency rollbacks.

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
- `release-manifest.json`
- `SHA256SUMS`

## Verification artifacts

Every new release publishes two verification files alongside the binaries:

- `release-manifest.json`: machine-readable source page, channel, version,
  target, asset size, SHA256, and upstream package metadata.
- `SHA256SUMS`: plain checksum file for all release assets except itself,
  including `release-manifest.json`.

Example Linux x64 verification:

```bash
curl -fsSLO https://github.com/dwgx/windsurf-ls-release/releases/latest/download/language_server_linux_x64
curl -fsSLO https://github.com/dwgx/windsurf-ls-release/releases/latest/download/SHA256SUMS
sha256sum --ignore-missing -c SHA256SUMS
```

## Workflow triggers

- `schedule`: runs daily
- `workflow_dispatch`: manual runs through the GitHub UI or `gh workflow run`
- `push`: non-default branches run validation automatically

## Safe validation on branches

Feature-branch runs parse both stable and next release channels and build artifacts, but they do not create a GitHub Release. Download the `windsurf-assets-stable` and `windsurf-assets-next` artifacts from the run to inspect extracted binaries.

```bash
gh run list --branch "$(git branch --show-current)" --limit 5
RUN_ID="$(gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID"
gh api repos/dwgx/windsurf-ls-release/actions/runs/"$RUN_ID"/artifacts
```

## Publishing from the default branch

After merging to the default branch, trigger the workflow manually or wait for the daily schedule. Stable releases use tags like `v<version>`, while next releases use tags like `next-v<version>`. If a tag already exists, that channel exits early. Otherwise it creates a draft release, uploads extracted assets, and publishes the release.

Stable publishes as a regular latest release. Next publishes as a prerelease and
is never marked latest.

## Local Linux x64 updater

```bash
LS_CHANNEL=stable ./tools/update_ls_linux_x64.sh
LS_BINARY_PATH=/tmp/language_server_linux_x64 LS_CHANNEL=next ./tools/update_ls_linux_x64.sh
```

The updater prefers the `ghfast.top` proxy for asset downloads and falls back to direct GitHub downloads if the proxy fails. It also verifies the downloaded `language_server_linux_x64` binary against the sha256 published in the release notes before replacing the local file.
