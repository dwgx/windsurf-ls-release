from __future__ import annotations

import unittest
from pathlib import Path


WORKFLOW = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
    encoding="utf-8"
)


class ReleaseWorkflowTests(unittest.TestCase):
    def test_next_releases_are_prereleases_and_never_latest(self) -> None:
        self.assertIn('if [ "$RELEASE_CHANNEL" = "next" ]; then', WORKFLOW)
        self.assertIn("create_flags=--prerelease --latest=false", WORKFLOW)
        self.assertIn("edit_flags=--prerelease", WORKFLOW)

    def test_stable_releases_are_marked_latest(self) -> None:
        self.assertIn("create_flags=--latest", WORKFLOW)
        self.assertIn("edit_flags=--latest", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
