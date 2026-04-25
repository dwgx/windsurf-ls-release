# windsurf-linux-server-release

This repository tracks the latest stable and next Windsurf releases from `https://windsurf.com/editor/releases`, extracts canonical `language_server_*` binaries from archive downloads, and publishes them as GitHub Release assets.

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
gh api repos/CaiJingLong/windsurf-linux-server-release/actions/runs/"$RUN_ID"/artifacts
```

## Publishing from the default branch

After merging to the default branch, trigger the workflow manually or wait for the daily schedule. Stable releases use tags like `v<version>`, while next releases use tags like `next-v<version>`. If a tag already exists, that channel exits early. Otherwise it creates a draft release, uploads extracted assets, and publishes the release.
