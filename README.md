# windsurf-ls-release

Maintained release mirror for extracted Windsurf / Devin Desktop `language_server_*`
binaries used by WindsurfAPI.

This repository tracks the latest stable and next Devin Desktop releases from
`https://docs.devin.ai/desktop/releases` and
`https://docs.devin.ai/desktop/releases-next`, extracts canonical
`language_server_*` binaries from archive downloads, and publishes them as
GitHub Release assets.

Stable releases are normal releases and may be marked as GitHub's Latest
release. Next-channel releases are prereleases and are explicitly published with
`--latest=false`, so `/releases/latest/download/...` remains stable-only.

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
