#!/usr/bin/env python3
"""Offline publication gate: data, evidence, rendered status and public files."""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
from urllib.parse import urlsplit
from refresh_core import BEIJING, clock_now, build_today, derived_status

BASE = pathlib.Path(os.environ.get("EVENTS_DIR", pathlib.Path(__file__).resolve().parent))
NOW = clock_now()
TODAY = build_today(NOW)


def validate(events, status, page, docs, baseline=None):
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    ids = []
    fields = ("id", "title", "platform", "task", "requirements", "award", "url", "status", "warning", "note", "venue")
    for e in events:
        eid = str(e.get("id", "?"))
        ids.append(eid)
        for field in fields:
            check(isinstance(e.get(field), str), f"{eid}: {field} must be a string")
        check(bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", eid)), f"{eid}: invalid ASCII slug")
        check(e.get("status") in {"open", "submission", "upcoming", "unclear", "practice", "closed"}, f"{eid}: invalid status")
        check(isinstance(e.get("tags"), list) and all(isinstance(t, str) for t in e.get("tags", [])), f"{eid}: invalid tags")
        check(isinstance(e.get("old"), list), f"{eid}: missing old list")
        check(type(e.get("priority")) is int, f"{eid}: priority must be integer")
        check(urlsplit(e.get("url", "")).scheme in {"https", "http"}, f"{eid}: invalid detail URL")
        sources = e.get("sources")
        check(isinstance(sources, list) and bool(sources), f"{eid}: missing official sources")
        for source in sources or []:
            url = source.get("url", "") if isinstance(source, dict) else source
            check(isinstance(url, str) and urlsplit(url).scheme in {"https", "http"}, f"{eid}: invalid source URL")
        for field in ("entry", "submit"):
            node = e.get(field)
            check(isinstance(node, dict), f"{eid}: missing {field} node")
            if not isinstance(node, dict):
                continue
            check(isinstance(node.get("text"), str), f"{eid}: missing {field}.text")
            try:
                day = dt.date.fromisoformat(node["day"]) if node.get("day") else None
                if node.get("instant"):
                    instant = dt.datetime.fromisoformat(node["instant"])
                    check(instant.tzinfo is not None, f"{eid}: {field}.instant lacks timezone")
                    if instant.tzinfo is not None:
                        check(day == instant.astimezone(BEIJING).date(), f"{eid}: {field}.day differs from Beijing instant date")
            except (ValueError, TypeError):
                errors.append(f"{eid}: invalid {field} date")
        try:
            if e.get("verifiedAt"):
                verified = dt.datetime.fromisoformat(e["verifiedAt"])
                check(verified.date() <= TODAY, f"{eid}: verification date is in the future")
            check(derived_status(e, TODAY, NOW) == e.get("status"), f"{eid}: status conflicts with known deadlines")
        except (ValueError, TypeError):
            errors.append(f"{eid}: invalid verification/deadline timestamp")
    check(len(ids) == len(set(ids)), "duplicate event IDs")
    check(len(re.findall(r'<tr data-id=', page)) == len(events), "HTML row count differs from events")
    check(set(re.findall(r'<tr data-id="([^"]+)"', page)) == set(ids), "HTML IDs differ from events")
    check(f"竞赛清单 · {TODAY.isoformat()}</title>" in page, "page build date differs")
    for tag in ("</table>", "</tbody>", "</script>", "</html>"):
        check(tag in page, f"missing {tag}")
    check({p.name for p in docs.iterdir()} == {"index.html", ".nojekyll"}, "docs must contain only index.html and .nojekyll")
    check(all(p.is_file() and not p.is_symlink() for p in docs.iterdir()), "docs contains directory or symbolic link")
    check(status.get("state") in {"ok", "partial", "failed"}, "invalid refresh state")
    try:
        finished = dt.datetime.fromisoformat(status["finishedAt"])
        check(finished.tzinfo is not None and finished.utcoffset() == dt.timedelta(hours=8), "finishedAt must use +08:00")
        check(finished.microsecond == 0, "finishedAt must have second precision")
        check(finished.date() == TODAY, "finishedAt is not today")
        display = finished.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S") + "（北京时间）"
        check(f"本轮核验完成时间 <b>{display}</b>" in page, "page verification time differs from finishedAt")
    except (KeyError, ValueError, TypeError):
        errors.append("invalid finishedAt")
    check(f'data-refresh-state="{status.get("state")}"' in page, "page does not expose refresh state")
    verified_ids = status.get("verifiedIds", [])
    check(isinstance(verified_ids, list) and len(verified_ids) == len(set(verified_ids)), "invalid verifiedIds")
    check(status.get("verified") == len(verified_ids), "verified count differs from verifiedIds")
    check(set(verified_ids).issubset(set(ids)), "verifiedIds include absent events")
    results = status.get("sourceResults", [])
    check(status.get("sourcesTotal") == len(results), "sourcesTotal differs from sourceResults")
    check(status.get("sourcesOk") == sum(r.get("state") == "ok" for r in results), "sourcesOk differs from sourceResults")
    check(status.get("runner") == "codex-agent", "unexpected runner")
    if status.get("state") == "ok":
        check(status.get("sourcesOk") == status.get("sourcesTotal") and not status.get("failedSources") and not status.get("pendingIds"), "ok state hides incomplete work")
    for eid in verified_ids:
        e = next((e for e in events if e["id"] == eid), None)
        if e:
            record = e.get("verification") or {}
            check(record.get("state") == "verified" and bool(record.get("evidence")), f"{eid}: no verified evidence")
            check(record.get("verifiedAt") == e.get("verifiedAt") and record.get("runId") == status.get("runId"), f"{eid}: verification provenance mismatch")
    if baseline:
        check(set(baseline["ids"]).issubset(set(ids)), "original event IDs were deleted")
        check(hashlib.sha256((BASE / "archive.backup.json").read_bytes()).hexdigest() == baseline["archiveSha256"], "archive.backup.json changed")
    return errors


def main():
    try:
        events = json.loads((BASE / "events.json").read_text(encoding="utf-8"))
        status = json.loads((BASE / "refresh-status.json").read_text(encoding="utf-8"))
        docs = BASE / "docs"
        page = (docs / "index.html").read_text(encoding="utf-8")
        baseline_path = os.environ.get("SCOUT_BASELINE")
        baseline = json.loads(pathlib.Path(baseline_path).read_text()) if baseline_path else None
        errors = validate(events, status, page, docs, baseline)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors = [str(exc)]
    for error in errors:
        print("FAIL:", error)
    if not errors:
        print(f"PASS: {len(events)} 条，数据/核验时间/来源覆盖/公开目录完整，数据截至 {TODAY}")
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
