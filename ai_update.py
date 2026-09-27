#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 核验与发现（GitHub Actions 上运行，用 GitHub Models 免费层）。

职责（与本地任务分工：本地只补扫 Kaggle/天池/讯飞三个 SPA 列表源）：
1. 核验：submit.day 14 天内 或 verifiedAt 超 7 天的条目，每天最多 12 条，
   拉官方详情页正文 → LLM 抽取日期/资格/奖金/风险 → 严格校验后写回。
2. 发现：grand-challenge API + Codabench API + NeurIPS 官博 → LLM 判断是否新赛事/是否限学生。
3. 全部写回 events.json；拿不准的一律 status=unclear，禁止推测补全。

环境变量：
  LLM_API_KEY / LLM_BASE_URL —— OpenAI 兼容端点的 key 与地址（如 DeepSeek/智谱/Kimi）。
    未配置时 AI 环节自动跳过（记录到 runs-log，不阻断发布链路）。
    实测备注：GITHUB_TOKEN 调 GitHub Models 在当前环境返回假应答（任何请求都回 OK），
    故不能依赖 GITHUB_TOKEN；需要真实的 LLM_API_KEY。
  GH_MODEL     —— 模型名（默认 openai/gpt-4.1，配 key 后按 provider 改，如 deepseek-chat）
  BUILD_TODAY  —— 测试用基准日期
"""
import datetime
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
import urllib.error
import html as HTMLMOD

BASE = pathlib.Path(__file__).resolve().parent
TODAY = datetime.date.fromisoformat(os.environ.get("BUILD_TODAY", datetime.date.today().isoformat()))
MODEL = os.environ.get("GH_MODEL", "openai/gpt-4.1")
LLM_URL = os.environ.get("LLM_BASE_URL", "https://models.github.ai/inference") .rstrip("/") + "/chat/completions"
LLM_KEY = os.environ.get("LLM_API_KEY", "")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
ACTIVE = {"open", "submission"}

log = {"date": TODAY.isoformat(), "verified": [], "verify_failed": [],
       "candidates": [], "added": [], "sources_failed": []}


def llm(prompt, max_tokens=700, tries=3):
    """调 OpenAI 兼容端点。未配 key 直接返回 None（跳过 AI 环节）。"""
    if not LLM_KEY:
        return None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                LLM_URL,
                data=json.dumps({
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "response_format": {"type": "text/plain"},
                }).encode(),
                headers={"Authorization": "Bearer " + LLM_KEY,
                         "Content-Type": "application/json", **UA},
            )
            body = urllib.request.urlopen(req, timeout=120).read().decode()
            data = json.loads(body)  # 非法 JSON（如代理假应答）→ 重试
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.setdefault("llm_errors", []).append("%s (try %d)" % (repr(e)[:120], i + 1))
            time.sleep(4 * (i + 1))
    return None


def parse_json(text):
    """从 LLM 输出稳健解析 JSON（剥代码围栏）。失败返回 None。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def text_of(raw):
    s = re.sub(r"(?is)<script.*?</script>", " ", raw)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", HTMLMOD.unescape(s)).strip()


# ---------- 1) 核验 ----------

def pick_verify_targets(events, limit=12):
    """14 天内到期 或 verifiedAt 超 7 天；优先级小者优先、方向相关加分。"""
    FAV = {"医学", "3D", "大模型", "Agent"}
    picks = []
    for e in events:
        sd = (e.get("submit") or {}).get("day") or ""
        va = e.get("verifiedAt") or "2000-01-01"
        urgent = False
        try:
            if sd and 0 <= (datetime.date.fromisoformat(sd) - TODAY).days <= 14:
                urgent = True
        except ValueError:
            pass
        try:
            stale = (TODAY - datetime.date.fromisoformat(va)).days > 7
        except ValueError:
            stale = True
        if e.get("status") in ACTIVE and (urgent or stale):
            score = e.get("priority", 5) * 10
            if FAV & set(e.get("tags") or []):
                score -= 3
            if urgent:
                score -= 5
            picks.append((score, e["id"]))
    picks.sort()
    return [pid for _, pid in picks[:limit]]


VERIFY_PROMPT = """You are verifying a competition entry against its official page text.
Given: the current entry (JSON) and the page text. Extract ONLY what the page actually states.
Rules:
- Dates: normalize to YYYY-MM-DD. Keep the page's timezone wording in *_text. If page gives no explicit date, use null and say so in notes. NEVER guess.
- eligibility: student-only? vendor/restricted? team size? affiliation+realname required?
- award & obligations (attend at own cost? open-source requirement?)
- warning: only real risks found on the page (conflicting dates, expired-but-button-live, missing timezone, defense required). Empty string if none.
Reply JSON only:
{"entry_day":"YYYY-MM-DD|null","entry_text":"...","submit_day":"YYYY-MM-DD|null","submit_text":"...",
 "eligibility":"...","award":"...","warning":"","notes":"page said..."}
If page text is unrelated or an error/login page, reply {"error":"page not usable"}.

CURRENT ENTRY:
%s

PAGE TEXT (first 6000 chars):
%s"""


def verify_all(events):
    by_id = {e["id"]: e for e in events}
    targets = pick_verify_targets(events)
    if not targets:
        return
    if not llm("Reply with exactly: PING"):  # key 未配或端点不可用 → 整轮跳过核验
        log["verify_failed"].append("LLM unavailable on runner")
        return
    for pid in targets:
        e = by_id[pid]
        url = (e.get("sources") or [e.get("url")])[0]
        try:
            body = text_of(fetch(url))[:6000]
        except Exception as ex:
            log["verify_failed"].append(pid + ": fetch " + repr(ex)[:80])
            continue
        if len(body) < 200:
            log["verify_failed"].append(pid + ": page too short")
            continue
        out = parse_json(llm(VERIFY_PROMPT % (json.dumps({k: e.get(k) for k in
                       ("title", "entry", "submit", "status")}, ensure_ascii=False), body)))
        if not out or out.get("error"):
            log["verify_failed"].append(pid + ": llm " + str(out)[:60] if out else "unparsed")
            continue
        changed = False
        for day_key, node in (("entry_day", "entry"), ("submit_day", "submit")):
            v = out.get(day_key)
            if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
                if e[node].get("day") != v:
                    e[node]["day"] = v
                    changed = True
                e[node].setdefault("text", "")
        for txt_key, node in (("entry_text", "entry"), ("submit_text", "submit")):
            v = out.get(txt_key)
            if v and e[node].get("text") != v:
                e[node]["text"] = v[:220]
                changed = True
        for f in ("requirements", "award"):
            v = out.get(f)
            if v and e.get(f) != v and len(v) > 10:
                e[f] = v[:500]
                changed = True
        w = out.get("warning") or ""
        if w and w != e.get("warning"):
            e["warning"] = w[:400]
            changed = True
        if changed:
            e["verifiedAt"] = TODAY.isoformat()
            e["verifiedBy"] = "ai"
            log["verified"].append(e["title"][:40])
        else:
            e["verifiedAt"] = TODAY.isoformat()  # 无变化也算核过
        time.sleep(1)


# ---------- 2) 发现新赛事 ----------

def collect_candidates(events):
    """结构化源里当前活跃、且不在库里的条目名。"""
    known = {e["title"].lower()[:40] for e in events}
    known |= {e["id"] for e in events}
    cands = []

    def is_new(name, url=""):
        n = (name or "").lower().strip()
        return bool(n) and n[:40] not in known and not any(k in url.lower() for k in events_ids_urls)

    global events_ids_urls
    events_ids_urls = {e.get("url", "").rstrip("/")[-40:].lower() for e in events if e.get("url")}

    # grand-challenge：API 全量 264 场，status 字段直接可用
    try:
        d = json.loads(fetch("https://grand-challenge.org/api/v1/challenges/?format=json&page_size=100"))
        for r in d.get("results", []):
            if not r.get("closed_access") and r.get("url"):
                cands.append(("gc", r.get("title") or r.get("slug", ""), r["url"]))
    except Exception as ex:
        log["sources_failed"].append("grand-challenge: " + repr(ex)[:80])

    # Codabench：公开赛列表（取最新 3 页）
    try:
        seen = 0
        url = "https://www.codabench.org/api/competitions/?format=json&page_size=50"
        for _ in range(3):
            d = json.loads(fetch(url))
            for r in d.get("results", []):
                cands.append(("cb", r.get("title", ""), "https://www.codabench.org/competitions/%s" % r.get("id")))
                seen += 1
            if not d.get("next"):
                break
            url = d["next"]
    except Exception as ex:
        log["sources_failed"].append("codabench: " + repr(ex)[:80])

    # NeurIPS 官博标题
    try:
        for m in re.finditer(r"<h2[^>]*>\s*<a[^>]*>([^<]{5,120})</a>", fetch("https://blog.neurips.cc/")):
            cands.append(("nips", m.group(1).strip(), "https://blog.neurips.cc/"))
    except Exception as ex:
        log["sources_failed"].append("neurips-blog: " + repr(ex)[:80])

    fresh = [(src, t, u) for src, t, u in cands if t and is_new(t, u)]
    log["candidates"] = [t[:40] for _, t, _ in fresh[:30]]
    return fresh[:15]  # 每轮最多让 LLM 判 15 个


TRIAGE_PROMPT = """Decide if this is a NEW AI/ML/CV/medical-imaging competition ENTRY worth tracking
(not a dataset, not a workshop-only page, not a past event that merely stays online).
Also judge: student-only? (eligibility)
Title: %s
Source page: %s (source: %s)
Reply JSON only: {"is_new_event": true/false, "student_only": true/false, "reason": "..."}"""


def discover(events):
    if not llm("Reply with exactly: PING"):
        log["sources_failed"].append("LLM unavailable (discovery skipped)")
        return
    fresh = collect_candidates(events)
    for src, title, url in fresh:
        out = parse_json(llm(TRIAGE_PROMPT % (title, url, src), max_tokens=200))
        if not out:
            continue
        if out.get("is_new_event") and not out.get("student_only"):
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
            events.append({
                "id": slug or ("auto-%d" % int(time.time())),
                "title": title,
                "platform": "会议官网" if src != "cb" else "Codabench",
                "venue": "",
                "tags": [],
                "task": "",
                "entry": {"text": "待核验", "day": None, "instant": None},
                "submit": {"text": "待核验", "day": None, "instant": None},
                "requirements": "",
                "award": "",
                "url": url,
                "status": "unclear",
                "warning": "新发现条目，日期与资格待下一轮核验（发现源：%s）" % src,
                "priority": 5,
                "verifiedAt": TODAY.isoformat(),
                "verifiedBy": "ai",
                "sources": [url],
            })
            log["added"].append(title[:40])


def main():
    events = json.loads((BASE / "events.json").read_text(encoding="utf-8"))
    n0 = len(events)
    verify_all(events)
    discover(events)
    (BASE / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log["n_total"] = len(events)
    with open(BASE / "runs-log.jsonl", encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    kept = []
    for l in lines:
        try:
            if json.loads(l).get("date") == TODAY.isoformat():
                continue
        except Exception:
            pass
        kept.append(l)
    prev = {}
    for l in lines:
        try:
            if json.loads(l).get("date") == TODAY.isoformat():
                prev = json.loads(l)
        except Exception:
            pass
    merged = dict(prev)
    merged.update({k: v for k, v in log.items() if v or k in ("n_total",)})
    kept.append(json.dumps(merged, ensure_ascii=False))
    with open(BASE / "runs-log.jsonl", "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")
    print(json.dumps(log, ensure_ascii=False, indent=2))
    if log.get("llm_errors") and not log["verified"] and not log["added"]:
        print("WARNING: LLM 全程不可用，本轮仅记录源状态", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
