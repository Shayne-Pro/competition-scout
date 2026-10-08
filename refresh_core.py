"""Shared, offline deadline semantics. Calendar dates use Beijing time."""
import datetime as dt
import json
import os

BEIJING = dt.timezone(dt.timedelta(hours=8))


def is_excluded(event):
    """Keep stored identities while hiding confirmed student-only events."""
    exclusion = event.get("exclusion") or {}
    return isinstance(exclusion, dict) and exclusion.get("reason") == "student-only"


def clock_now():
    raw = os.environ.get("BUILD_NOW")
    now = dt.datetime.fromisoformat(raw) if raw else dt.datetime.now(BEIJING)
    if now.tzinfo is None:
        raise ValueError("BUILD_NOW must include a timezone")
    return now.astimezone(BEIJING)


def build_today(now=None):
    return dt.date.fromisoformat(os.environ["BUILD_TODAY"]) if os.environ.get("BUILD_TODAY") else (now or clock_now()).date()


def deadline_passed(node, today, now):
    node = node or {}
    if node.get("kind") == "start":
        return None
    if node.get("instant"):
        instant = dt.datetime.fromisoformat(node["instant"])
        if instant.tzinfo is None:
            raise ValueError("deadline instant must include a timezone")
        return instant < now
    if node.get("day"):
        return dt.date.fromisoformat(node["day"]) < today
    return None


def derived_status(event, today, now):
    status = event.get("status")
    if status not in {"open", "submission", "upcoming"}:
        return status
    entry, submit = event.get("entry") or {}, event.get("submit") or {}
    ep = deadline_passed(entry, today, now) if entry.get("mandatory", True) else None
    sp = deadline_passed(submit, today, now)
    if sp is True:
        return "unclear" if ep is False else "closed"
    if status == "open" and ep is True:
        return "submission" if sp is False else "unclear"
    # A future deadline is not evidence that an upcoming event has opened.
    start = event.get("start") or {}
    if status == "upcoming" and start and sp is False:
        instant = start.get("instant")
        started = dt.datetime.fromisoformat(instant) <= now if instant else bool(start.get("day") and dt.date.fromisoformat(start["day"]) <= today)
        if started:
            return "submission" if ep is True else "open"
    return status


def action_days(event, today, now):
    result = []
    for key in ("entry", "submit"):
        node = event.get(key) or {}
        if node.get("day") and deadline_passed(node, today, now) is False:
            result.append((dt.date.fromisoformat(node["day"]) - today).days)
    return min(result) if result else -1


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
