#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


RELEASE_CHANNELS = {
    "stable": {
        "url": "https://docs.devin.ai/desktop/releases",
        "field_name": "stableReleases",
        "tag_prefix": "",
        "release_name_prefix": "Devin Desktop",
    },
    "next": {
        "url": "https://docs.devin.ai/desktop/releases-next",
        "field_name": "nextReleases",
        "tag_prefix": "next-",
        "release_name_prefix": "Devin Desktop Next",
    },
}

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

MDX_DOWNLOAD_PROPS = {
    "darwinArm64": ("MacOS", "macOS for Apple Silicon (Archive, .zip)"),
    "darwinX64": ("MacOS", "macOS for Intel (Archive, .zip)"),
    "linuxX64": ("Linux", "Linux x64 (.tar.gz)"),
    "win32Arm64Archive": ("Windows", "Windows arm64 (Archive, .zip)"),
    "win32X64Archive": ("Windows", "Windows x64 (Archive, .zip)"),
}


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "devin-desktop-release-bot/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def extract_escaped_json_array(html: str, field_name: str) -> list[dict]:
    marker = f'{field_name}\\":'
    start = html.find(marker)
    if start == -1:
        raise ValueError(f"Could not find field {field_name!r} in releases HTML.")

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
                raw = html[array_start : index + 1]
                decoded = raw.encode("utf-8").decode("unicode_escape")
                return json.loads(decoded)

    raise ValueError(f"Could not find the closing bracket for field {field_name!r}.")


def package_name_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    return Path(path).name


def extract_mdx_release_components(html: str) -> list[dict]:
    decoded_html = html.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    release_pattern = re.compile(r"Release,\s*\{(?P<body>.*?)\n\s*\}\)", re.DOTALL)
    prop_pattern = re.compile(r'^\s*(?P<name>\w+):\s*"(?P<url>[^"]+)"\s*,?$', re.MULTILINE)
    title_pattern = re.compile(r'title:\s*"Download (?P<version>[^"]+)"')
    label_pattern = re.compile(r'label:\s*"v(?P<version>[^"]+)"')

    releases = []
    seen_versions: set[str] = set()
    for match in release_pattern.finditer(decoded_html):
        props = {
            prop_match.group("name"): prop_match.group("url")
            for prop_match in prop_pattern.finditer(match.group("body"))
        }
        if "linuxX64" not in props:
            continue

        prelude = decoded_html[max(0, match.start() - 4000) : match.start()]
        version_match = None
        for pattern in (title_pattern, label_pattern):
            matches = list(pattern.finditer(prelude))
            if matches:
                version_match = matches[-1]
                break
        if version_match is None:
            continue

        version = version_match.group("version")
        if version in seen_versions:
            continue
        seen_versions.add(version)

        release = {"version": version, "MacOS": [], "Windows": [], "Linux": []}
        for prop_name, (platform_name, display_name) in MDX_DOWNLOAD_PROPS.items():
            url = props.get(prop_name)
            if not url:
                continue
            release[platform_name].append(
                {
                    "displayName": display_name,
                    "url": url,
                    "name": package_name_from_url(url),
                    "productVersion": version,
                }
            )
        releases.append(release)

    return releases


def extract_releases(html: str, field_name: str) -> list[dict]:
    try:
        return extract_escaped_json_array(html, field_name)
    except ValueError as json_error:
        releases = extract_mdx_release_components(html)
        if releases:
            return releases
        raise ValueError(
            f"{json_error} Could not find Devin Desktop MDX release download blocks."
        ) from json_error


def build_manifest(releases: list[dict], channel: str, source_url: str) -> dict:
    if not releases:
        raise ValueError(f"The {channel} releases array is empty.")

    latest = releases[0]
    version = latest["version"]
    channel_config = RELEASE_CHANNELS[channel]

    all_entries: list[dict] = []
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
                "package_name": entry.get("name"),
                "package_product_version": entry.get("productVersion"),
                "package_version": entry.get("version"),
                "package_notes": entry.get("notes"),
                "package_timestamp": entry.get("timestamp"),
                "package_sha256": entry.get("sha256hash"),
            }
        )

    return {
        "channel": channel,
        "source_url": source_url,
        "version": version,
        "tag": f"{channel_config['tag_prefix']}v{version}",
        "release_name": f"{channel_config['release_name_prefix']} {version}",
        "targets": targets,
    }


def write_github_output(manifest: dict) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"channel={manifest['channel']}\n")
        handle.write(f"version={manifest['version']}\n")
        handle.write(f"tag={manifest['tag']}\n")
        handle.write(f"release_name={manifest['release_name']}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=sorted(RELEASE_CHANNELS), default="stable")
    parser.add_argument("--url")
    parser.add_argument("--manifest-out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    channel_config = RELEASE_CHANNELS[args.channel]
    source_url = args.url or channel_config["url"]
    html = fetch_html(source_url)
    releases = extract_releases(html, channel_config["field_name"])
    manifest = build_manifest(releases, args.channel, source_url)

    manifest_path = Path(args.manifest_out)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_github_output(manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
