#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


CHUNK_SIZE = 1024 * 1024
STAMP_FIELDS = {
    "STABLE_BUILD_SCM_REVISION": "build_revision",
    "STABLE_BUILD_SCM_STATUS": "build_status",
    "BUILD_TIMESTAMP": "build_timestamp",
    "BUILD_HOST": "build_host",
    "BUILD_USER": "build_user",
}


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def describe_file(path: Path) -> dict:
    size_bytes = path.stat().st_size
    return {
        "name": path.name,
        "size_bytes": size_bytes,
        "size_human": format_size(size_bytes),
        "sha256": sha256_file(path),
    }


def format_unix_timestamp(raw_value: str | int | None) -> str | None:
    if raw_value is None:
        return None

    try:
        timestamp = int(raw_value)
    except (TypeError, ValueError):
        return None

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def run_binary_command(binary_path: Path, argument: str) -> str:
    completed = subprocess.run(
        [str(binary_path), argument],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = completed.stdout.strip()
    if not output:
        output = completed.stderr.strip()
    return output


def parse_stamp_output(output: str) -> dict:
    metadata: dict[str, str | int] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapped_key = STAMP_FIELDS.get(key.strip())
        if not mapped_key:
            continue
        cleaned_value = value.strip()
        if mapped_key == "build_timestamp":
            try:
                metadata[mapped_key] = int(cleaned_value)
            except ValueError:
                metadata[mapped_key] = cleaned_value
        else:
            metadata[mapped_key] = cleaned_value

    build_timestamp_utc = format_unix_timestamp(metadata.get("build_timestamp"))
    if build_timestamp_utc:
        metadata["build_timestamp_utc"] = build_timestamp_utc
    return metadata


def extract_package_info(target: dict) -> dict:
    package_info = {
        "name": target.get("package_name"),
        "product_version": target.get("package_product_version"),
        "revision_hint": target.get("package_version") or target.get("package_notes"),
        "sha256": target.get("package_sha256"),
    }
    package_info = {key: value for key, value in package_info.items() if value not in (None, "")}

    package_timestamp = target.get("package_timestamp")
    if package_timestamp not in (None, ""):
        try:
            package_info["timestamp"] = int(package_timestamp)
        except (TypeError, ValueError):
            package_info["timestamp"] = package_timestamp

        package_timestamp_utc = format_unix_timestamp(package_timestamp)
        if package_timestamp_utc:
            package_info["timestamp_utc"] = package_timestamp_utc

    return package_info


def extract_binary_metadata(target: dict, binary_path: Path) -> tuple[dict, str | None]:
    if target["target"] != "linux-x64":
        return {}, None

    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        return {}, "binary introspection skipped on non-linux-x64 host"

    metadata: dict[str, str | int] = {}
    warnings: list[str] = []

    try:
        version_output = run_binary_command(binary_path, "--version")
        if version_output:
            metadata["self_reported_version"] = version_output.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError) as exc:
        warnings.append(f"binary version probe failed: {exc}")

    try:
        stamp_output = run_binary_command(binary_path, "--stamp")
        metadata.update(parse_stamp_output(stamp_output))
    except (OSError, subprocess.SubprocessError) as exc:
        warnings.append(f"binary stamp probe failed: {exc}")

    warning = "; ".join(warnings) if warnings else None
    return metadata, warning


def process_target(target: dict, dist_dir: Path, scratch_root: Path) -> dict:
    work_dir = scratch_root / target["target"]
    work_dir.mkdir(parents=True, exist_ok=True)

    archive_name = Path(urllib.parse.urlparse(target["source_url"]).path).name
    archive_path = work_dir / archive_name
    extracted_dir = work_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    download_file(target["source_url"], archive_path)
    extract_archive(archive_path, extracted_dir, target["archive_type"])
    binary_path = find_expected_binary(extracted_dir, target["expected_binary_name"])

    output_path = dist_dir / target["expected_binary_name"]
    shutil.copy2(binary_path, output_path)

    if not output_path.name.endswith(".exe"):
        output_path.chmod(output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    warnings: list[str] = []
    binary_info = describe_file(output_path)
    binary_metadata, metadata_warning = extract_binary_metadata(target, output_path)
    if binary_metadata:
        binary_info.update(binary_metadata)
    if metadata_warning:
        warnings.append(metadata_warning)

    created_assets = [output_path.name]
    gzip_path = output_path.with_name(output_path.name + ".gz")
    gzip_info = None
    try:
        gzip_copy(output_path, gzip_path)
        created_assets.append(gzip_path.name)
        gzip_info = describe_file(gzip_path)
    except OSError as exc:
        warnings.append(f"gzip failed: {exc}")

    entry = {
        "target": target["target"],
        "display_name": target["display_name"],
        "binary_name": target["expected_binary_name"],
        "assets": created_assets,
        "binary_info": binary_info,
    }

    package_info = extract_package_info(target)
    if package_info:
        entry["package_info"] = package_info

    if gzip_info:
        entry["gzip_info"] = gzip_info

    if warnings:
        entry["warning"] = "; ".join(warnings)

    return entry


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
        "channel": manifest.get("channel", "stable"),
        "source_url": manifest.get("source_url"),
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
                entry = process_target(target, dist_dir, scratch_root)
                summary["successful_targets"].append(entry)
            except Exception as exc:  # noqa: BLE001
                summary["failed_targets"].append(
                    {
                        "target": target["target"],
                        "required": target["required"],
                        "reason": f"{target['target']}: {exc}",
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
