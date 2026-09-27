#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日确定性刷新（无网络、无 AI，纯日期运算）。

由 GitHub Actions 定时工作流每天调用，也在本地每日任务里复用：
1. 状态翻转：open/submission 且报名与提交日期均已过去 → closed（标 verifiedBy=auto）；
   upcoming 已进入报名或提交窗口 → open。
2. 窗口提醒：7 天内到期且此前未提醒过的条目，记进 notified.json（每条截止日只提醒一次）。
3. 运行日志：把当日摘要追加进 runs-log.jsonl，供回查「哪天发生了什么」。

设计约束：只做纯函数式日期运算，绝不改写文案、绝不删条目、绝不推测日期。
"""
import json
import datetime
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent
TODAY = datetime.date.fromisoformat(
    __import__("os").environ.get("BUILD_TODAY", datetime.date.today().isoformat())
)

ACTIVE = {"open", "submission"}


def load(p, default):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def d(day):
    try:
        return datetime.date.fromisoformat(day)
    except Exception:
        return None


def main():
    events = load(BASE / "events.json", [])
    notified = load(BASE / "notified.json", {"reminded": []})
    reminded = set(map(tuple, notified.get("reminded", [])))

    flipped, upcoming_live = [], []
    for e in events:
        ed = d((e.get("entry") or {}).get("day") or "")
        sd = d((e.get("submit") or {}).get("day") or "")
        last = max([x for x in (ed, sd) if x], default=None)
        st = e.get("status")

        if st in ACTIVE and last is not None and last < TODAY:
            e["status"] = "closed"
            e["verifiedBy"] = "auto"
            flipped.append(e["title"])
        elif st == "upcoming":
            starts = [x for x in (ed, sd) if x and x <= TODAY]
            if starts:
                e["status"] = "open"
                upcoming_live.append(e["title"])

    # 7 天内到期提醒（一次性，按 id+截止日去重）
    due7 = []
    for e in events:
        if e.get("status") not in ACTIVE:
            continue
        for key in ("entry", "submit"):
            node = e.get(key) or {}
            day = d(node.get("day") or "")
            if day and 0 <= (day - TODAY).days <= 7:
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
    }
    with open(BASE / "runs-log.jsonl", encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    entry = json.dumps(log, ensure_ascii=False)
    # 同一天多次运行（Actions + 本地任务）只保留最后一条
    kept = []
    for l in lines:
        try:
            if json.loads(l).get("date") == TODAY.isoformat():
                continue
        except Exception:
            pass
        kept.append(l)
    kept.append(entry)
    with open(BASE / "runs-log.jsonl", "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")

    print(json.dumps(log, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
