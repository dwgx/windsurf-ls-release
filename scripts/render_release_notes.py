#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def append_detail(lines: list[str], label: str, value: object) -> None:
    if value in (None, ""):
        return
    lines.append(f"  {label}: {value}")


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
            lines.append(f"- {item['target']}: {asset_list}")

            package_info = item.get("package_info", {})
            append_detail(lines, "package name", package_info.get("name"))
            append_detail(lines, "package product version", package_info.get("product_version"))
            append_detail(lines, "package revision hint", package_info.get("revision_hint"))
            append_detail(lines, "package timestamp", package_info.get("timestamp"))
            append_detail(lines, "package time (UTC)", package_info.get("timestamp_utc"))
            append_detail(lines, "package sha256", package_info.get("sha256"))

            binary_info = item.get("binary_info", {})
            if binary_info:
                raw_asset = binary_info.get("name")
                if raw_asset:
                    raw_summary = f"{raw_asset} ({binary_info.get('size_human')}, sha256: {binary_info.get('sha256')})"
                    append_detail(lines, "extracted binary", raw_summary)
                append_detail(lines, "binary self-reported version", binary_info.get("self_reported_version"))
                append_detail(lines, "binary build revision", binary_info.get("build_revision"))
                append_detail(lines, "binary build status", binary_info.get("build_status"))
                append_detail(lines, "binary build timestamp", binary_info.get("build_timestamp"))
                append_detail(lines, "binary build time (UTC)", binary_info.get("build_timestamp_utc"))

            gzip_info = item.get("gzip_info", {})
            if gzip_info:
                gzip_summary = f"{gzip_info.get('name')} ({gzip_info.get('size_human')}, sha256: {gzip_info.get('sha256')})"
                append_detail(lines, "gzip asset", gzip_summary)

            append_detail(lines, "warning", item.get("warning"))
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
