"""Public API pagination must preserve failures and never imply rule verification."""
import json
from pathlib import Path
import tempfile
import unittest
from fetch_source_lists import collect


class SourceLists(unittest.TestCase):
    def run_collect(self, fetch, max_pages=100):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new-directory" / "list.json"
            result = collect("evalai-present", output, max_pages, fetch)
            self.assertEqual(json.loads(output.read_text()), result)
            return result

    def test_all_pages_and_count_required(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"count": 2, "next": "?page=2" if len(calls) == 1 else None, "results": [{"id": len(calls), "title": "Official title"}]}
        result = self.run_collect(fetch)
        self.assertEqual(result["state"], "complete")
        self.assertEqual(len(result["items"]), 2)
        self.assertIn("remain unverified", result["coverage"])

    def test_midway_failure_keeps_progress_and_cursor(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) > 1:
                raise TimeoutError("source unavailable")
            return {"count": 2, "next": "?page=2", "results": [{"id": 1, "title": "Official title"}]}
        result = self.run_collect(fetch)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(result["next"].endswith("?page=2"))

    def test_empty_but_count_mismatch_not_complete(self):
        result = self.run_collect(lambda url: {"count": 4, "next": None, "results": []})
        self.assertEqual(result["state"], "failed")

    def test_valid_empty_inventory_is_complete(self):
        result = self.run_collect(lambda url: {"count": 0, "next": None, "results": []})
        self.assertEqual(result["state"], "complete")

    def test_page_limit_is_partial_and_retains_next(self):
        result = self.run_collect(lambda url: {"count": 2, "next": "?page=2", "results": [{"id": 1, "title": "Official title"}]}, 1)
        self.assertEqual(result["state"], "partial")
        self.assertIsNotNone(result["next"])

    def test_off_domain_next_is_rejected_before_fetch(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"count": 2, "next": "https://unrelated.example/api/?token=secret", "results": [{"id": 1, "title": "Official title"}]}
        result = self.run_collect(fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["state"], "partial")
        self.assertIn("outside", result["error"])

    def test_duplicate_page_items_not_complete(self):
        result = self.run_collect(lambda url: {"count": 2, "next": "?page=2", "results": [{"id": 1, "title": "Official title"}]})
        self.assertEqual(result["state"], "partial")
        self.assertIn("duplicate", result["error"])

    def test_codabench_backend_next_uses_public_origin(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"count": 2, "next": "https://codabench-prod.lisn.upsaclay.fr/api/competitions/public/?page=2" if len(calls) == 1 else None, "results": [{"id": len(calls), "title": "Official title"}]}
        with tempfile.TemporaryDirectory() as folder:
            result = collect("codabench", Path(folder) / "list.json", fetch=fetch)
        self.assertEqual(result["state"], "complete")
        self.assertEqual(calls[1], "https://www.codabench.org/api/competitions/public/?page=2")
        self.assertIn("codabench-prod", result["pages"][0]["returnedNext"])


if __name__ == "__main__":
    unittest.main()
