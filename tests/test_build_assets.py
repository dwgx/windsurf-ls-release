from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_build_assets_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build_assets.py"
    spec = importlib.util.spec_from_file_location("build_assets", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_assets = load_build_assets_module()


class FormatUnixTimestampTests(unittest.TestCase):
    def test_formats_millisecond_timestamp(self) -> None:
        self.assertEqual(
            build_assets.format_unix_timestamp(1778907276000),
            "2026-05-16 04:54 UTC",
        )


class ArchiveSafetyTests(unittest.TestCase):
    def test_archive_member_must_stay_inside_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            build_assets.assert_archive_member_safe(output_dir, "nested/language_server_linux_x64")
            with self.assertRaises(ValueError):
                build_assets.assert_archive_member_safe(output_dir, "../evil")


class ReleaseMetadataTests(unittest.TestCase):
    def test_write_release_metadata_publishes_manifest_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            binary_path = dist_dir / "language_server_linux_x64"
            gzip_path = dist_dir / "language_server_linux_x64.gz"
            binary_path.write_bytes(b"linux-binary")
            gzip_path.write_bytes(b"gzip-binary")

            binary_sha256 = hashlib.sha256(binary_path.read_bytes()).hexdigest()
            gzip_sha256 = hashlib.sha256(gzip_path.read_bytes()).hexdigest()
            summary = {
                "channel": "stable",
                "source_url": "https://docs.devin.ai/desktop/releases",
                "version": "9.9.9",
                "tag": "v9.9.9",
                "release_name": "Devin Desktop 9.9.9",
                "successful_targets": [
                    {
                        "target": "linux-x64",
                        "display_name": "Linux x64",
                        "binary_name": "language_server_linux_x64",
                        "assets": [
                            "language_server_linux_x64",
                            "language_server_linux_x64.gz",
                        ],
                        "binary_info": {
                            "name": "language_server_linux_x64",
                            "size_bytes": binary_path.stat().st_size,
                            "size_human": build_assets.format_size(binary_path.stat().st_size),
                            "sha256": binary_sha256,
                        },
                        "gzip_info": {
                            "name": "language_server_linux_x64.gz",
                            "size_bytes": gzip_path.stat().st_size,
                            "size_human": build_assets.format_size(gzip_path.stat().st_size),
                            "sha256": gzip_sha256,
                        },
                        "package_info": {
                            "name": "devin-linux-x64.tar.gz",
                            "sha256": "a" * 64,
                        },
                    }
                ],
                "failed_targets": [],
            }

            build_assets.write_release_metadata(summary, dist_dir)

            manifest_path = dist_dir / build_assets.RELEASE_MANIFEST_NAME
            checksums_path = dist_dir / build_assets.CHECKSUMS_NAME
            self.assertTrue(manifest_path.exists())
            self.assertTrue(checksums_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["tag"], "v9.9.9")
            self.assertEqual(manifest["assets"][0]["name"], "language_server_linux_x64")
            self.assertEqual(manifest["assets"][0]["sha256"], binary_sha256)
            self.assertEqual(manifest["targets"][0]["package_info"]["name"], "devin-linux-x64.tar.gz")

            checksums = checksums_path.read_text(encoding="utf-8").splitlines()
            manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            self.assertIn(f"{binary_sha256}  language_server_linux_x64", checksums)
            self.assertIn(f"{gzip_sha256}  language_server_linux_x64.gz", checksums)
            self.assertIn(f"{manifest_sha256}  {build_assets.RELEASE_MANIFEST_NAME}", checksums)
            self.assertFalse(any(line.endswith(f"  {build_assets.CHECKSUMS_NAME}") for line in checksums))


if __name__ == "__main__":
    unittest.main()
