#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 核验与发现（GitHub Actions 上运行，用 GitHub Models 免费层）。

职责（与本地任务分工：本地只补扫 Kaggle/天池/讯飞三个 SPA 列表源）：
1. 核验：submit.day 14 天内 或 verifiedAt 超 7 天的条目，每天最多 12 条，
   拉官方详情页正文 → LLM 抽取日期/资格/奖金/风险 → 严格校验后写回。
2. 发现：grand-challenge API + Codabench API + NeurIPS 官博 → LLM 判断是否新赛事/是否限学生。
3. 全部写回 events.json；拿不准的一律 status=unclear，禁止推测补全。

环境变量：
  LLM_API_KEY / LLM_BASE_URL —— OpenAI 兼容端点。当前配置：智谱 coding 端点
    （https://open.bigmodel.cn/api/coding/paas/v4），模型 glm-5.3-flash。
    注意智谱是思考模型：thinking enabled 时答案在 reasoning_content；本脚本统一
    thinking disabled（已实测有效，content 直接可用）。
  GH_MODEL     —— 模型名（默认 glm-5.3-flash；请求 glm-4.6/4.5 会被路由到 5.3-flash）
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
MODEL = os.environ.get("GH_MODEL", "glm-5.3-flash")
LLM_URL = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4").rstrip("/") + "/chat/completions"
LLM_KEY = os.environ.get("LLM_API_KEY", "")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
ACTIVE = {"open", "submission"}

log = {"date": TODAY.isoformat(), "verified": [], "verify_failed": [],
       "candidates": [], "added": [], "sources_failed": []}


def llm(prompt, max_tokens=700, tries=3):
    """调 OpenAI 兼容端点（智谱）。未配 key 直接返回 None（跳过 AI 环节）。"""
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
                    "thinking": {"type": "disabled"},  # 智谱思考模型：关思考后 content 直接可用
                }).encode(),
                headers={"Authorization": "Bearer " + LLM_KEY,
                         "Content-Type": "application/json", **UA},
            )
            body = urllib.request.urlopen(req, timeout=120).read().decode()
            data = json.loads(body)  # 非法 JSON（如代理假应答）→ 重试
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content and msg.get("reasoning_content"):
                # 某些情况思考未关掉：答案落在了 reasoning_content，做兜底提取
                content = msg["reasoning_content"]
            return content or None
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
        # verifiedAt 兼容两种形态：顶层字符串（老数据）与 verification.verifiedAt（Agent 时期数据）
        va = e.get("verifiedAt") or (e.get("verification") or {}).get("verifiedAt") or "2000-01-01"
        va = str(va)[:10]  # Agent 时期是带时区的 ISO，取日期部分
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
        if isinstance(e.get("verification"), dict):  # 同步 Agent 时期的嵌套核验记录
            e["verification"]["verifiedAt"] = TODAY.isoformat() + "T12:00:00+08:00"
            e["verification"]["verifiedBy"] = "ai"
        time.sleep(1)


# ---------- 2) 发现新赛事 ----------

def collect_candidates(events):
    """结构化源里当前活跃、且不在库里的条目名。URL 用「注册域+一级路径」规范化去重。"""
    def canon(url):
        """URL 归一化用于去重。grand-challenge 系子站（x.grand-challenge.org）以子域为身份，
        路径无关——子站根域与 /timeline/ 等路径必须归一成同一个。其余站点取 域+一级路径。"""
        m = re.match(r"https?://([^/]+)(/[^/?#]*)?", url or "")
        if not m:
            return ""
        host = m.group(1).replace("www.", "")
        seg = (m.group(2) or "/").strip("/").split("/")[0]
        parts = host.split(".")
        # x.grand-challenge.org / x.grand-challenge.org.cn 这类：≥3 段且含 grand-challenge → 只用 host
        if "grand-challenge" in host and len(parts) >= 3:
            return host
        return (host + "/" + seg.lower()).rstrip("/")

    known_urls = {canon(e.get("url")) for e in events if e.get("url")}
    for e in events:
        for u in (e.get("sources") or []):
            if isinstance(u, str) and u:          # 老数据里 sources 可能是 dict 列表
                known_urls.add(canon(u))
    def title_norm(s):
        return re.sub(r"[\s\u3000·・\-_—]+", "", (s or "").lower())  # 去空白与连接符再比

    known = {title_norm(e["title"])[:40] for e in events}
    known |= {e["id"] for e in events}
    cands = []

    def is_new(name, url=""):
        n = title_norm(name)
        if not n or n[:40] in known:
            return False
        cu = canon(url)
        return not (cu and cu in known_urls)

    # grand-challenge：API 全量 264 场。三个字段都不可单独信：
    # status（LOLA11 2011 年老赛标 OPEN）、end_date（ToothFairy2 挂 2028-09-30）、
    # 部分条目日期缺失。用组合硬规则：窗口在近一年内 + 近期有维护。
    try:
        url = "https://grand-challenge.org/api/v1/challenges/?format=json&page_size=100"
        while url:
            d = json.loads(fetch(url))
            for r in d.get("results", []):
                sd, ed = (r.get("start_date") or "")[:10], (r.get("end_date") or "")[:10]
                mod = (r.get("modified") or "")[:10]
                sd_ok = sd and "2025-01-01" <= sd <= TODAY.isoformat()      # 近两年内开赛且已开赛
                ed_ok = ed and TODAY.isoformat() <= ed <= "2027-12-31"      # 未结束且年份不离谱
                mod_ok = mod >= "2025-09-01"                                 # 近一年有维护
                if (sd_ok and ed_ok and mod_ok) and r.get("url"):
                    cands.append(("gc", r.get("title") or r.get("slug", ""), r["url"],
                                  {"start": sd, "end": ed, "mod": mod}))
            url = d.get("next")
    except Exception as ex:
        log["sources_failed"].append("grand-challenge: " + repr(ex)[:80])

    # Codabench：公开赛列表（取最新 3 页，只留近期创建的）
    try:
        url = "https://www.codabench.org/api/competitions/?format=json&page_size=50"
        for _ in range(3):
            d = json.loads(fetch(url))
            for r in d.get("results", []):
                created = (r.get("created_when") or "")[:10]
                if created >= "2025-01-01":  # 老 API 无状态字段，用创建时间粗筛
                    cands.append(("cb", r.get("title", ""),
                                  "https://www.codabench.org/competitions/%s" % r.get("id"),
                                  {"start": created, "end": "", "mod": created}))
            if not d.get("next"):
                break
            url = d["next"]
    except Exception as ex:
        log["sources_failed"].append("codabench: " + repr(ex)[:80])

    # NeurIPS 官博标题：只保留明确是赛事的（Announcing/Events/Recap 等公告性标题剔除）
    try:
        for m in re.finditer(r"<h2[^>]*>\s*<a[^>]*>([^<]{5,120})</a>", fetch("https://blog.neurips.cc/")):
            t = m.group(1).strip()
            if re.search(r"(?i)challenge|competition|contest|cup", t) and not re.search(
                    r"(?i)announc|recap|events|program|committee|deadline for|results", t):
                cands.append(("nips", t, "https://blog.neurips.cc/", {}))
    except Exception as ex:
        log["sources_failed"].append("neurips-blog: " + repr(ex)[:80])

    # SPA 三源（scrape_spa.py 用 Playwright 抓的正文快照，缺失则跳过）
    spa_path = BASE / "spa_snapshot.json"
    if spa_path.exists():
        try:
            spa = json.loads(spa_path.read_text(encoding="utf-8"))
            log["spa_sources_ok"] = [s["source"] for s in spa.get("snapshots", [])]
            for s in spa.get("snapshots", []):
                for line in s["text"].split("\n"):
                    line = line.strip()
                    # 经验规则：SPA 卡片行——含赛事关键词且长度像标题（10-90 字符）；
                    # 确定性剔除非赛事行：路演/招募/关于/已结束等（LLM 对这类行判断不可靠，实测漏过）
                    if (10 <= len(line) <= 90 and re.search(
                            r"挑战赛|大赛|竞赛|Challenge|Competition|Cup|Hackathon", line)
                            and not re.search(
                            r"路演|关于|招募|实习|已结束|活动日历|一键报名|更多赛事|我要|登录|举办方|截止时间|奖金|Track \d|@|\.com|\.cn", line)):
                        cands.append((s["source"], line, s["url"], {}))
            for f in spa.get("failed", []):
                log["sources_failed"].append("spa-" + f[:60])
        except Exception as ex:
            log["sources_failed"].append("spa-snapshot: " + repr(ex)[:60])

    fresh = [(src, t, u, (m if len(item) > 3 else {})) for item in cands
             for src, t, u in [item[:3]] if t and is_new(t, u)]
    log["candidates"] = [t[:40] for _, t, _, _ in fresh[:30]]
    return fresh[:15]  # 每轮最多让 LLM 判 15 个


TRIAGE_PROMPT = """Decide if this is a NEW, CURRENTLY-ACTIVE AI/ML/CV/medical-imaging competition ENTRY worth tracking.
Reject if ANY of: it is a past/ended event merely kept online; a dataset/benchmark only; a workshop page without a live competition; a debug/test entry.
Dates context: today is {today}. Entry dates: start={start}, end={end}, last-modified={mod}.
Also judge: student-only? (eligibility)
Title: {title}
URL: {url} (source: {src})
Reply JSON only: {{"is_new_event": true/false, "student_only": true/false, "reason": "..."}}"""


def discover(events):
    if not llm("Reply with exactly: PING"):
        log["sources_failed"].append("LLM unavailable (discovery skipped)")
        return
    fresh = collect_candidates(events)
    # 附带日期上下文：gc 源在收集时把 start/end/mod 存进 meta
    for item in fresh:
        src, title, url = item[0], item[1], item[2]
        meta = item[3] if len(item) > 3 and isinstance(item[3], dict) else {}
        out = parse_json(llm(TRIAGE_PROMPT.format(
            today=TODAY.isoformat(),
            start=meta.get("start") or "unknown", end=meta.get("end") or "unknown",
            mod=meta.get("mod") or "unknown",
            title=title, url=url, src=src), max_tokens=250))
        if not out:
            continue
        if out.get("is_new_event") and not out.get("student_only"):
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
            plat = {"kaggle": "Kaggle", "tianchi": "天池", "xfyun": "讯飞"}.get(src, "会议官网" if src != "cb" else "Codabench")
            events.append({
                "id": slug or ("auto-%d" % int(time.time())),
                "title": title,
                "platform": plat,
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

    # 同步写 refresh-status.json：build_page.py 的「Agent 更新」横幅读这个文件
    n_verified = len(log.get("verified") or [])
    state = "ok" if n_verified or log.get("added") else (
        "failed" if log.get("llm_errors") else "ok")
    (BASE / "refresh-status.json").write_text(json.dumps({
        "state": state,
        "finishedAt": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "verified": n_verified,
        "sourcesOk": len(log.get("spa_sources_ok") or []) + (2 if not any("grand-challenge" in f for f in log.get("sources_failed") or []) else 0),
        "sourcesTotal": 6,
        "runner": "local-scripts",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
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
