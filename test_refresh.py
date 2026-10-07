"""Regression tests for failures reproduced during the Codex migration."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ci_check
import daily_refresh
import scrape_spa
from refresh_core import BEIJING, derived_status, action_days

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=BEIJING)
TODAY = NOW.date()


def fixture():
    return {"id": "sample", "title": "Sample", "platform": "会议官网", "tags": [], "task": "Task", "entry": {"text": "", "day": None, "instant": None}, "submit": {"text": "Deadline", "day": "2026-10-20", "instant": None}, "requirements": "Open", "award": "", "url": "https://example.org/competition", "status": "open", "warning": "", "note": "", "venue": "", "old": [], "priority": 1, "sources": ["https://example.org/competition"], "verifiedAt": "2026-10-07T12:00:00+08:00", "verifiedBy": "agent", "verification": {"state": "verified", "runId": "test", "verifiedAt": "2026-10-07T12:00:00+08:00", "evidence": [{"url": "https://example.org/competition", "summary": "Official deadline confirmed"}]}}


class Deadlines(unittest.TestCase):
    def test_entry_expired_submission_still_open(self):
        e = fixture(); e["entry"]["day"] = "2026-10-06"
        self.assertEqual(derived_status(e, TODAY, NOW), "submission")

    def test_unknown_final_cannot_close(self):
        e = fixture(); e["entry"]["day"] = "2026-10-06"; e["submit"]["day"] = None
        self.assertEqual(derived_status(e, TODAY, NOW), "unclear")

    def test_expired_upcoming_never_opens(self):
        e = fixture(); e["status"] = "upcoming"; e["submit"]["day"] = "2026-10-02"
        self.assertEqual(derived_status(e, TODAY, NOW), "closed")

    def test_future_deadline_does_not_prove_started(self):
        e = fixture(); e["status"] = "upcoming"
        self.assertEqual(derived_status(e, TODAY, NOW), "upcoming")

    def test_instant_has_priority_and_no_expired_reminder(self):
        e = fixture(); e["submit"].update(day="2026-10-07", instant="2026-10-07T01:00:00+08:00")
        self.assertEqual(derived_status(e, TODAY, NOW), "closed")
        self.assertEqual(action_days(e, TODAY, NOW), -1)

    def test_date_only_not_closed_during_deadline_day(self):
        e = fixture(); e["submit"]["day"] = "2026-10-07"
        self.assertEqual(derived_status(e, TODAY, NOW), "open")

    def test_optional_registration_not_a_join_barrier(self):
        e = fixture(); e["entry"].update(day="2026-10-06", mandatory=False)
        self.assertEqual(derived_status(e, TODAY, NOW), "open")

    def test_missing_log_created_and_verifier_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); e = fixture(); e["submit"]["day"] = "2026-10-02"
            (base / "events.json").write_text(json.dumps([e]))
            with patch.object(daily_refresh, "BASE", base), patch.object(daily_refresh, "NOW", NOW), patch.object(daily_refresh, "TODAY", TODAY):
                self.assertEqual(daily_refresh.main(), 0)
            self.assertTrue((base / "runs-log.jsonl").exists())
            self.assertEqual(json.loads((base / "events.json").read_text())[0]["verifiedBy"], "agent")


class PublicationGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.docs = Path(self.tmp.name)
        (self.docs / "index.html").write_text(""); (self.docs / ".nojekyll").write_text("")
        self.e = fixture()
        self.s = {"state": "ok", "finishedAt": "2026-10-07T12:00:00+08:00", "verified": 1, "verifiedIds": ["sample"], "sourcesOk": 1, "sourcesTotal": 1, "sourceResults": [{"state": "ok"}], "runner": "codex-agent", "runId": "test"}
        self.page = '<title>竞赛清单 · 2026-10-07</title><tr data-id="sample">本轮核验完成时间 <b>2026-10-07 12:00:00（北京时间）</b><span data-refresh-state="ok"></span></table></tbody></script></html>'

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self):
        with patch.object(ci_check, "TODAY", TODAY), patch.object(ci_check, "NOW", NOW):
            return ci_check.validate([self.e], self.s, self.page, self.docs)

    def test_valid_fixture(self):
        self.assertEqual(self.errors(), [])

    def test_invalid_calendar_date_rejected(self):
        self.e["submit"]["day"] = "2026-99-99"
        self.assertTrue(self.errors())

    def test_aoe_calendar_mismatch_rejected(self):
        self.e["submit"].update(day="2026-10-20", instant="2026-10-20T23:59:00-12:00")
        self.assertTrue(any("Beijing" in error for error in self.errors()))

    def test_stale_verification_rejected_even_with_today_title(self):
        self.s["finishedAt"] = "2020-01-01T12:00:00+08:00"
        self.assertTrue(any("today" in error for error in self.errors()))

    def test_extra_public_file_rejected(self):
        (self.docs / "private.json").write_text("{}")
        self.assertTrue(any("only" in error for error in self.errors()))

    def test_symbolic_public_file_rejected(self):
        (self.docs / ".nojekyll").unlink(); (self.docs / ".nojekyll").symlink_to(self.docs / "index.html")
        self.assertTrue(any("symbolic" in error for error in self.errors()))

    def test_ok_cannot_hide_source_failure(self):
        self.s.update(sourcesOk=0, sourceResults=[{"state": "failed"}], failedSources=["unread"])
        self.assertTrue(any("incomplete" in error for error in self.errors()))

    def test_missing_evidence_rejected(self):
        self.e["verification"]["evidence"] = []
        self.assertTrue(any("evidence" in error for error in self.errors()))


class Scraping(unittest.TestCase):
    def test_long_navigation_shell_is_not_a_list(self):
        self.assertFalse(scrape_spa.has_list_content("tianchi", "首页 登录 天池大赛 " * 100, [{"text": "天池大赛", "url": "https://tianchi.aliyun.com/competition/algorithmList"}]))

    def test_blocked_page_is_not_success_even_with_detail_link(self):
        self.assertFalse(scrape_spa.has_list_content("kaggle", "Verify you are human " * 50, [{"text": "RSNA", "url": "https://www.kaggle.com/competitions/rsna"}]))

    def test_devpost_login_link_is_not_a_competition_card(self):
        self.assertFalse(scrape_spa.has_list_content("devpost", "Log in and browse hackathons " * 100, [{"text": "Log in", "url": "https://secure.devpost.com/users/login"}]))

    def test_first_page_body_is_partial_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            result = {"fetchedAt": "2026-10-07T12:00:00+08:00", "snapshots": [{"source": "tianchi"}], "failed": ["kaggle: no credentials", "xfyun: empty"]}
            with patch.object(scrape_spa, "OUT", Path(directory) / "snapshot.json"):
                scrape_spa.finish(result)
            row = next(r for r in result["results"] if r["source"] == "tianchi")
            self.assertEqual(row["fetchState"], "ok")
            self.assertEqual(row["state"], "partial")

    def test_driver_startup_failure_writes_source_results(self):
        import sys
        from types import SimpleNamespace
        class BrokenDriver:
            def __enter__(self):
                raise RuntimeError("driver startup failed")
            def __exit__(self, *args):
                return False
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "snapshot.json"
            fake = SimpleNamespace(sync_playwright=lambda: BrokenDriver())
            with patch.object(scrape_spa, "OUT", out), patch.object(scrape_spa, "fetch_kaggle_api", side_effect=RuntimeError("unavailable")), patch.dict(sys.modules, {"playwright": SimpleNamespace(), "playwright.sync_api": fake}):
                self.assertEqual(scrape_spa.main(), 2)
            result = json.loads(out.read_text())
            self.assertEqual(len(result["results"]), 3)
            self.assertTrue(all(r["state"] == "failed" for r in result["results"]))

    def test_missing_browser_library_still_writes_fresh_failures(self):
        import builtins
        original = builtins.__import__
        def importing(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("test missing dependency")
            return original(name, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "snapshot.json"; out.write_text('{"stale":true}')
            with patch.object(scrape_spa, "OUT", out), patch.object(scrape_spa, "fetch_kaggle_api", side_effect=RuntimeError("unavailable")), patch("builtins.__import__", side_effect=importing):
                self.assertEqual(scrape_spa.main(), 2)
            snapshot = json.loads(out.read_text())
            self.assertIn("fetchedAt", snapshot)
            self.assertEqual(len(snapshot["results"]), 3)
            self.assertTrue(all(r["state"] == "failed" for r in snapshot["results"]))


if __name__ == "__main__":
    unittest.main()
