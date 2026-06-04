from __future__ import annotations

import importlib.util
import textwrap
import unittest
from pathlib import Path


def load_discover_release_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "discover_release.py"
    spec = importlib.util.spec_from_file_location("discover_release", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load discover_release module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


discover_release = load_discover_release_module()


DEVIN_RELEASE_PROPS = """
  darwinArm64: "https://example.test/darwin-arm64/Devin-darwin-arm64-3.0.21.zip",
  darwinX64: "https://example.test/darwin-x64/Devin-darwin-x64-3.0.21.zip",
  linuxX64: "https://example.test/linux-x64/Devin-linux-x64-3.0.21.tar.gz",
  win32Arm64Archive: "https://example.test/win32-arm64/Devin-win32-arm64-3.0.21.zip",
  win32X64Archive: "https://example.test/win32-x64/Devin-win32-x64-3.0.21.zip"
"""


class DiscoverReleaseTests(unittest.TestCase):
    def test_extracts_legacy_escaped_json_releases(self) -> None:
        html = (
            'self.__next_f.push([1,"{\\"stableReleases\\":[{\\"version\\":\\"9.9.9\\",'
            '\\"Linux\\":[{\\"displayName\\":\\"Linux x64 (.tar.gz)\\",'
            '\\"url\\":\\"https://example.test/linux.tar.gz\\"}]}]}"])'
        )

        releases = discover_release.extract_releases(html, "stableReleases")

        self.assertEqual(releases[0]["version"], "9.9.9")
        self.assertEqual(releases[0]["Linux"][0]["url"], "https://example.test/linux.tar.gz")

    def test_extracts_mdx_release_page_downloads(self) -> None:
        html = textwrap.dedent(
            f"""
            _jsx(Update, {{
              label: "v3.0.21",
              description: "June 4, 2026",
              id: "v3-0-21",
              children: _jsx(Release, {{
            {DEVIN_RELEASE_PROPS}
              }})
            }})
            """
        )

        releases = discover_release.extract_releases(html, "stableReleases")

        self.assertEqual(releases[0]["version"], "3.0.21")
        self.assertEqual(releases[0]["Linux"][0]["displayName"], "Linux x64 (.tar.gz)")
        self.assertEqual(
            releases[0]["Windows"][1]["url"],
            "https://example.test/win32-x64/Devin-win32-x64-3.0.21.zip",
        )

    def test_extracts_mdx_changelog_downloads(self) -> None:
        html = textwrap.dedent(
            f"""
            _jsx(Accordion, {{
              title: "Download 3.0.1019",
              defaultOpen: true,
              children: _jsx(Release, {{
            {DEVIN_RELEASE_PROPS.replace("3.0.21", "3.0.1019+next.25c2de6c4b")}
              }})
            }})
            """
        )

        releases = discover_release.extract_releases(html, "nextReleases")

        self.assertEqual(releases[0]["version"], "3.0.1019")
        self.assertEqual(releases[0]["MacOS"][0]["productVersion"], "3.0.1019")

    def test_package_name_from_url_decodes_and_trims_paths(self) -> None:
        self.assertEqual(
            discover_release.package_name_from_url("https://example.test/releases/Devin%20Linux.tar.gz"),
            "Devin Linux.tar.gz",
        )
        self.assertEqual(
            discover_release.package_name_from_url("https://example.test/releases/Devin-linux-x64/"),
            "Devin-linux-x64",
        )

    def test_builds_manifest_for_devin_desktop_release(self) -> None:
        releases = discover_release.extract_releases(
            textwrap.dedent(
                f"""
                _jsx(Update, {{
                  label: "v3.0.21",
                  children: _jsx(Release, {{
                {DEVIN_RELEASE_PROPS}
                  }})
                }})
                """
            ),
            "stableReleases",
        )

        manifest = discover_release.build_manifest(
            releases,
            "stable",
            "https://docs.devin.ai/desktop/releases",
        )

        self.assertEqual(manifest["tag"], "v3.0.21")
        self.assertEqual(manifest["release_name"], "Devin Desktop 3.0.21")
        self.assertEqual(
            manifest["targets"][0]["source_url"],
            "https://example.test/linux-x64/Devin-linux-x64-3.0.21.tar.gz",
        )


if __name__ == "__main__":
    unittest.main()
