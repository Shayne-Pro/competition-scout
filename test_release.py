"""Regression checks for accidental publication of operator state."""
from pathlib import Path
import tempfile
import unittest
import check_release
import scrape_spa


class ReleaseBoundary(unittest.TestCase):
    def test_private_paths_blocked_even_when_nested(self):
        for name in (".workbuddy/memory/day.md", ".codex/state.json", ".scout/evidence.json", "copy/.kaggle/kaggle.json", ".env", ".env.production", "notified.json", "runs-log.jsonl", "spa_snapshot.json", "secondary_snapshot.json", "credential.pem", "../outside"):
            with self.subTest(name=name):
                self.assertIsNotNone(check_release.forbidden_path(name))

    def test_public_data_and_example_configuration_allowed(self):
        for name in ("events.json", "sources.json", "refresh-status.json", "archive.backup.json", "examples/events.json", ".env.example"):
            with self.subTest(name=name):
                self.assertIsNone(check_release.forbidden_path(name))

    def test_home_path_detected_but_normal_official_url_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / "sample.txt"
            for home in ("/" + "Users" + "/operator/project/", "/" + "home" + "/operator/project/", "C:" + "\\Users\\operator\\project"):
                path.write_text(home)
                self.assertTrue(check_release.scan_files(root, [path.name]))
            path.write_text("https://example.org/home/competition")
            self.assertEqual(check_release.scan_files(root, [path.name]), [])

    def test_token_detection_never_prints_value(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); token = "ghp_" + "a" * 36
            (root / "sample.txt").write_text(token)
            errors = check_release.scan_files(root, ["sample.txt"])
            self.assertTrue(errors)
            self.assertNotIn(token, " ".join(errors))

    def test_symbolic_file_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target").write_text("sample")
            (root / "link").symlink_to(root / "target")
            self.assertTrue(check_release.scan_files(root, ["link"]))

    def test_scraper_default_output_is_local_state(self):
        self.assertEqual(scrape_spa.OUT.relative_to(scrape_spa.BASE).parts, (".scout", "spa_snapshot.json"))


if __name__ == "__main__":
    unittest.main()
