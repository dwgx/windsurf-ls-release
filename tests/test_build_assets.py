from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
