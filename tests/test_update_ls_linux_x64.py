from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "update_ls_linux_x64.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class UpdateLinuxX64ScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.call_log = self.root / "curl-calls.log"
        self.args_log = self.root / "curl-args.log"
        self.url_map_path = self.root / "url-map.json"
        self.fake_curl = self.root / "fake-curl.py"
        self.target_path = self.root / "installed" / "language_server_linux_x64"

        binary_bytes = b"fake-language-server-linux-x64"
        self.binary_path = self.root / "language_server_linux_x64"
        self.binary_path.write_bytes(binary_bytes)
        self.binary_sha256 = hashlib.sha256(binary_bytes).hexdigest()

        self.release_tag = "v9.9.9"
        self.release_base_url = "https://example.test/releases"
        self.proxy_prefix = "https://ghfast.top/"
        self.direct_asset_url = (
            f"{self.release_base_url}/download/{self.release_tag}/language_server_linux_x64"
        )
        self.proxy_asset_url = f"{self.proxy_prefix}{self.direct_asset_url}"

        self.releases_html = self.root / "releases.html"
        self.releases_html.write_text(
            (
                '<a href="/CaiJingLong/windsurf-linux-server-release/releases/tag/'
                f'{self.release_tag}">Windsurf 9.9.9</a>'
            ),
            encoding="utf-8",
        )

        self.release_page = self.root / "release-page.html"
        self.release_page.write_text(
            textwrap.dedent(
                f"""
                <p>Successful targets:</p>
                <ul>
                <li>linux-x64: language_server_linux_x64, language_server_linux_x64.gz<br>
                extracted binary: language_server_linux_x64 (180.07 MiB, sha256: {self.binary_sha256})<br>
                gzip asset: language_server_linux_x64.gz (37.87 MiB, sha256: deadbeef)</li>
                </ul>
                """
            ).strip(),
            encoding="utf-8",
        )

        write_executable(
            self.fake_curl,
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                from __future__ import annotations

                import json
                import os
                import shutil
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                output_path = None
                url = None
                index = 0
                while index < len(args):
                    arg = args[index]
                    if arg == "-o":
                        output_path = args[index + 1]
                        index += 2
                        continue
                    if not arg.startswith("-"):
                        url = arg
                    index += 1

                if url is None or output_path is None:
                    raise SystemExit("fake curl requires a URL and -o <path>")

                log_path = Path(os.environ["CALL_LOG"])
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(url + "\\n")

                args_log = os.environ.get("ARGS_LOG")
                if args_log:
                    with Path(args_log).open("a", encoding="utf-8") as handle:
                        handle.write(" ".join(args) + "\\n")

                fail_urls = set(filter(None, os.environ.get("FAIL_URLS", "").splitlines()))
                if url in fail_urls:
                    raise SystemExit(22)

                url_map = json.loads(Path(os.environ["URL_MAP_PATH"]).read_text(encoding="utf-8"))
                source = url_map.get(url)
                if source is None:
                    raise SystemExit(f"unmapped URL: {url}")

                shutil.copyfile(source, output_path)
                """
            ).strip()
            + "\n",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_url_map(self, *, include_proxy: bool = True) -> None:
        url_map = {
            self.release_base_url: str(self.releases_html),
            f"{self.release_base_url}/tag/{self.release_tag}": str(self.release_page),
            self.direct_asset_url: str(self.binary_path),
        }
        if include_proxy:
            url_map[self.proxy_asset_url] = str(self.binary_path)
        self.url_map_path.write_text(json.dumps(url_map), encoding="utf-8")

    def run_script(self, *, fail_urls: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CALL_LOG": str(self.call_log),
                "ARGS_LOG": str(self.args_log),
                "CURL_BIN": str(self.fake_curl),
                "GH_PROXY_PREFIX": self.proxy_prefix,
                "LS_BINARY_PATH": str(self.target_path),
                "LS_RELEASES_BASE_URL": self.release_base_url,
                "SHA256SUM_BIN": "shasum -a 256",
                "URL_MAP_PATH": str(self.url_map_path),
            }
        )
        if fail_urls:
            env["FAIL_URLS"] = "\n".join(fail_urls)

        return subprocess.run(
            ["/bin/sh", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def run_script_with_env(self, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        merged_env.update(env)
        return subprocess.run(
            ["/bin/sh", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=merged_env,
            check=False,
        )

    def test_logs_progress_and_uses_proxy_download(self) -> None:
        self.write_url_map(include_proxy=True)

        completed = self.run_script()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(self.target_path.exists())
        self.assertEqual(self.target_path.read_bytes(), self.binary_path.read_bytes())
        self.assertIn("Fetching release list", completed.stdout)
        self.assertIn("Downloading language_server_linux_x64", completed.stdout)
        self.assertIn("Verifying sha256", completed.stdout)
        self.assertIn("Installed", completed.stdout)
        calls = self.call_log.read_text(encoding="utf-8").splitlines()
        self.assertIn(self.proxy_asset_url, calls)
        self.assertNotIn(self.direct_asset_url, calls)
        if self.args_log.exists():
            args_lines = self.args_log.read_text(encoding="utf-8").splitlines()
            self.assertTrue(all("--progress-bar" not in line for line in args_lines))

    def test_skips_download_when_local_sha256_matches_remote(self) -> None:
        self.write_url_map(include_proxy=True)
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_path.write_bytes(self.binary_path.read_bytes())

        completed = self.run_script()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Local file already matches remote sha256", completed.stdout)
        calls = self.call_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            calls,
            [
                self.release_base_url,
                f"{self.release_base_url}/tag/{self.release_tag}",
            ],
        )

    def test_auto_detects_sha256_command_when_not_configured(self) -> None:
        self.write_url_map(include_proxy=True)
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_path.write_bytes(self.binary_path.read_bytes())

        completed = self.run_script_with_env(
            {
                "CALL_LOG": str(self.call_log),
                "ARGS_LOG": str(self.args_log),
                "CURL_BIN": str(self.fake_curl),
                "GH_PROXY_PREFIX": self.proxy_prefix,
                "LS_BINARY_PATH": str(self.target_path),
                "LS_RELEASES_BASE_URL": self.release_base_url,
                "PATH": os.environ["PATH"],
                "URL_MAP_PATH": str(self.url_map_path),
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Using sha256 command: shasum -a 256", completed.stdout)
        self.assertIn("Local file already matches remote sha256", completed.stdout)

    def test_fails_when_configured_sha256_command_is_unavailable(self) -> None:
        self.write_url_map(include_proxy=True)

        completed = self.run_script_with_env(
            {
                "CALL_LOG": str(self.call_log),
                "ARGS_LOG": str(self.args_log),
                "CURL_BIN": str(self.fake_curl),
                "GH_PROXY_PREFIX": self.proxy_prefix,
                "LS_BINARY_PATH": str(self.target_path),
                "LS_RELEASES_BASE_URL": self.release_base_url,
                "SHA256SUM_BIN": "missing-sha256-command",
                "URL_MAP_PATH": str(self.url_map_path),
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Required checksum command is not available: missing-sha256-command", completed.stderr)

    def test_uses_non_progress_download_flags_in_ci(self) -> None:
        self.write_url_map(include_proxy=True)
        env = os.environ.copy()
        env.update(
            {
                "CALL_LOG": str(self.call_log),
                "CI": "true",
                "CURL_BIN": str(self.fake_curl),
                "GH_PROXY_PREFIX": self.proxy_prefix,
                "LS_BINARY_PATH": str(self.target_path),
                "LS_RELEASES_BASE_URL": self.release_base_url,
                "SHA256SUM_BIN": "shasum -a 256",
                "URL_MAP_PATH": str(self.url_map_path),
            }
        )

        completed = subprocess.run(
            ["sh", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Downloading language_server_linux_x64", completed.stdout)
        if self.args_log.exists():
            args_lines = self.args_log.read_text(encoding="utf-8").splitlines()
            self.assertTrue(all("--progress-bar" not in line for line in args_lines))

    def test_falls_back_to_direct_download_when_proxy_fails(self) -> None:
        self.write_url_map(include_proxy=False)

        completed = self.run_script(fail_urls=[self.proxy_asset_url])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        calls = self.call_log.read_text(encoding="utf-8").splitlines()
        self.assertIn(self.proxy_asset_url, calls)
        self.assertIn(self.direct_asset_url, calls)
        self.assertIn("Proxy download failed", completed.stdout)

    def test_fails_when_sha256_does_not_match_release_notes(self) -> None:
        self.write_url_map(include_proxy=True)
        self.release_page.write_text(
            self.release_page.read_text(encoding="utf-8").replace(
                self.binary_sha256, "0" * 64
            ),
            encoding="utf-8",
        )

        completed = self.run_script()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("sha256 mismatch", completed.stderr)
        self.assertFalse(self.target_path.exists())


if __name__ == "__main__":
    unittest.main()
