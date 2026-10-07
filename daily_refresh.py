#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日确定性刷新（无网络、无 AI，纯日期运算）。

由 Codex 本地定时任务调用：
1. 只按已知截止推导状态；未知提交截止不得推断已收官。
   精确时刻优先，开始时间与截止时间分开，保留原核验来源。
2. 窗口提醒：7 天内到期且此前未提醒过的条目，记进 notified.json（每条截止日只提醒一次）。
3. 运行日志：把当日摘要追加进 runs-log.jsonl，供回查「哪天发生了什么」。

设计约束：只做纯函数式日期运算，绝不改写文案、绝不删条目、绝不推测日期。
"""
import json
import datetime
import pathlib
import sys
from refresh_core import clock_now, build_today, derived_status, deadline_passed, atomic_json

BASE = pathlib.Path(__file__).resolve().parent
NOW = clock_now()
TODAY = build_today(NOW)

ACTIVE = {"open", "submission"}


def load(p, default):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def save(p, obj):
    atomic_json(p, obj)


def d(day):
    try:
        return datetime.date.fromisoformat(day)
    except Exception:
        return None


def main():
    events = load(BASE / "events.json", [])
    notified = load(BASE / "notified.json", {"reminded": []})
    reminded = set(map(tuple, notified.get("reminded", [])))
    log_path = BASE / "runs-log.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []

    flipped, upcoming_live, changes = [], [], []
    for e in events:
        st = e.get("status")
        new = derived_status(e, TODAY, NOW)
        if new != st:
            e["status"] = new
            e["statusDerivation"] = {"at": NOW.isoformat(timespec="seconds"), "from": st, "to": new, "basis": "known_deadlines"}
            changes.append({"id": e["id"], "from": st, "to": new})
            if new == "closed":
                flipped.append(e["title"])
            elif st == "upcoming" and new == "open":
                upcoming_live.append(e["title"])
            elif new == "unclear" and not e.get("warning"):
                e["warning"] = "已知截止与参赛状态需要复核，不能仅按日期确认全部阶段结束。"

    # 7 天内到期提醒（一次性，按 id+截止日去重）
    due7 = []
    for e in events:
        if e.get("status") not in ACTIVE:
            continue
        for key in ("entry", "submit"):
            node = e.get(key) or {}
            day = d(node.get("day") or "")
            if day and deadline_passed(node, TODAY, NOW) is False and 0 <= (day - TODAY).days <= 7:
                tag = (e["id"], key, node["day"])
                if tag not in reminded:
                    due7.append((e["title"], key, node["day"]))
                    reminded.add(tag)

    notified["reminded"] = [list(t) for t in sorted(reminded)]
    notified["lastRun"] = TODAY.isoformat()
    save(BASE / "notified.json", notified)
    save(BASE / "events.json", events)

    log = {
        "date": TODAY.isoformat(),
        "n_total": len(events),
        "n_open": sum(1 for e in events if e.get("status") in ACTIVE),
        "flipped_closed": flipped,
        "upcoming_to_open": upcoming_live,
        "due7": [t[0] + " (" + t[2] + ")" for t in due7],
        "status_changes": changes,
    }
    entry = json.dumps(log, ensure_ascii=False)
    # 同日运行摘要保留最近一次；核验证据由 refresh-status 和 events 保存。
    kept = []
    for l in lines:
        try:
            if json.loads(l).get("date") == TODAY.isoformat():
                continue
        except Exception:
            pass
        kept.append(l)
    kept.append(entry)
    temporary = log_path.with_name(log_path.name + ".tmp")
    temporary.write_text("\n".join(kept) + "\n", encoding="utf-8")
    temporary.replace(log_path)

    print(json.dumps(log, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
