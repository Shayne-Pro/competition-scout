#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Playwright 无头浏览器抓 SPA 列表源（脚本直抓拿不到正文的源）。

默认输出 .scout/spa_snapshot.json：{"snapshots": [{source, url, text}], "failed": [...]}。
设计约束：
- 本地运行（浏览器路径依赖 playwright + chromium）；
- 单源失败不阻断（记入 failed）；
- Kaggle 优先走官方 API v1（需 ~/.kaggle/kaggle.json 或 KAGGLE_USERNAME/KAGGLE_KEY，
  无凭据或 API 失败时记录原因，由 agent 使用现有浏览器读取官网兜底）；
- 快照只覆盖已抓正文范围，不代表全平台扫描成功。
"""
import base64
import argparse
import json
import pathlib
import re
import sys
import urllib.request
import datetime
import os
from refresh_core import atomic_json, BEIJING

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / ".scout" / "spa_snapshot.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

SOURCES = [
    ("kaggle", "https://www.kaggle.com/competitions"),
    ("tianchi", "https://tianchi.aliyun.com/competition/algorithmList"),
    ("xfyun", "https://challenge.xfyun.cn/"),
]
SOURCE_URLS = dict(SOURCES, **{
    "devpost": "https://devpost.com/hackathons",
    "ascend": "https://www.hiascend.com/developer/AAIC2026",
    "baidu": "https://aistudio.baidu.com/competition",
    "tencent": "https://algo.qq.com/",
    "zindi": "https://zindi.world/competitions",
})


def has_list_content(name, body, links):
    """Navigation text and HTTP 200 alone do not prove a usable list."""
    if any(marker.lower() in body.lower() for marker in ("检查浏览器", "Checking your browser", "Verify you are human", "reCAPTCHA", "Access denied")):
        return False
    patterns = {
        "kaggle": r"/competitions/[^/?#]+",
        "tianchi": r"/competition/entrance/\d+",
        "baidu": r"/competition/detail/\d+",
        "devpost": r"https://(?!secure\.|help\.|info\.|www\.)[^/]+\.devpost\.com/",
        "ascend": r"/developer/(?:contests/details/|ops)",
        "zindi": r"/competitions/[^/?#]+",
    }
    if name in patterns:
        if name == "devpost" and not ("participants" in body and "in prizes" in body):
            return False
        return bool(len(body) > 500 and any(re.search(patterns[name], link.get("url", "")) and link.get("text", "").strip() for link in links))
    if name == "xfyun":
        return "报名截止时间" in body and "举办方" in body
    if name == "tencent":
        return all(marker in body for marker in ("TAAC x KDD Cup", "Timeline", "Eligibility", "Industrial"))
    return False


def kaggle_credentials():
    """返回 (username, key) 或 None。优先环境变量，其次 ~/.kaggle/kaggle.json。"""
    import os
    u, k = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
    if u and k:
        return u, k
    p = pathlib.Path.home() / ".kaggle" / "kaggle.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("username") and d.get("key"):
                return d["username"], d["key"]
        except Exception:
            pass
    return None


def fetch_kaggle_api():
    """官方 API v1 拉 general 组前两页；只是有限发现范围。

    返回 snapshots 元素；失败抛异常（由调用方记 failed）。
    """
    cred = kaggle_credentials()
    if not cred:
        raise RuntimeError("no kaggle credentials (put ~/.kaggle/kaggle.json or set "
                           "KAGGLE_USERNAME/KAGGLE_KEY); agent 应 WebFetch 兜底")
    auth = base64.b64encode(("%s:%s" % cred).encode()).decode()
    lines = []
    for page in (1, 2):
        url = ("https://www.kaggle.com/api/v1/competitions/list"
               "?sortBy=recentlyCreated&group=general&page=%d" % page)
        req = urllib.request.Request(url, headers={
            "Authorization": "Basic " + auth, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        for c in data:
            lines.append(" | ".join([
                c.get("ref") or "", c.get("category") or "",
                (c.get("title") or "")[:80],
                "deadline=" + (c.get("deadline") or "")[:10],
                "reward=" + str(c.get("reward") or ""),
                "teams=" + str(c.get("teamCount") or ""),
                "started=" + (c.get("enabledDate") or "")[:10]]))
        if len(data) < 20:
            break
    if not lines:
        raise RuntimeError("kaggle api returned 0 items")
    return {"source": "kaggle", "url": "https://www.kaggle.com/api/v1/competitions/list",
            "text": "\n".join(lines)[:12000]}


def run():
    fetched = datetime.datetime.now(BEIJING).isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = {"runId": os.environ.get("SCOUT_RUN_ID", fetched), "fetchedAt": fetched, "snapshots": [], "failed": [], "results": [], "attemptErrors": []}
    snap, failed = result["snapshots"], result["failed"]
    atomic_json(OUT, result)
    if any(name == "kaggle" for name, _ in SOURCES):
        try:
            item = fetch_kaggle_api()
            item.update(fetchedAt=fetched, coverage="general group, first two recently-created pages; not complete platform coverage")
            snap.append(item)
        except Exception as e:
            failed.append("kaggle: %s" % e)
    atomic_json(OUT, result)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        failed.extend([name + ": playwright unavailable" for name, _ in SOURCES if name != "kaggle"])
        return finish(result)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chromium", headless=True,
                                        args=["--disable-blink-features=AutomationControlled"])
        except Exception:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                failed.extend([name + ": chromium unavailable" for name, _ in SOURCES if name != "kaggle"])
                return finish(result)
        for name, url in SOURCES:
            if name == "kaggle" and any(item["source"] == "kaggle" for item in snap):
                continue
            pg = None
            ctx = None
            try:
                ctx = browser.new_context(
                    user_agent=UA, locale="en-US" if name == "kaggle" else "zh-CN",
                    viewport={"width": 1440, "height": 900})
                pg = ctx.new_page()
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                body = ""
                links = []
                for _ in range(8):  # 最多等 40s：SPA 渲染 / Cloudflare 检查页自动跳转
                    pg.wait_for_timeout(5000)
                    body = pg.inner_text("body")
                    links = pg.locator("a[href]").evaluate_all("elements => elements.map(a => ({text: a.innerText.trim(), url: a.href})).filter(a => a.text)")
                    if has_list_content(name, body, links):
                        break
                if not has_list_content(name, body, links):
                    failed.append(name + ": no valid competition content after 40s (navigation/check/login shell is not a list)")
                else:
                    attempts = [f for f in failed if f.startswith(name + ":")]
                    result["attemptErrors"].extend(attempts)
                    failed[:] = [f for f in failed if not f.startswith(name + ":")]
                    snap.append({"source": name, "url": url,
                                 "finalUrl": pg.url, "text": body[:12000], "links": links, "fetchedAt": datetime.datetime.now(BEIJING).isoformat(timespec="seconds"),
                                 "truncated": len(body) > 12000,
                                 "coverage": "visible first-page body and links; pagination, subcategories and detail verification incomplete"})
            except Exception as e:
                failed.append("%s: %r" % (name, e))
            finally:
                if pg:
                    pg.close()
                if ctx:
                    ctx.close()
                atomic_json(OUT, result)
        browser.close()
    return finish(result)


def finish(result):
    successful = {s["source"] for s in result["snapshots"]}
    result["finishedAt"] = datetime.datetime.now(BEIJING).isoformat(timespec="seconds")
    times = {s["source"]: s.get("fetchedAt", result["fetchedAt"]) for s in result["snapshots"]}
    result["results"] = [{"source": name, "state": "partial" if name in successful else "failed", "fetchState": "ok" if name in successful else "failed", "coverageState": "partial" if name in successful else "none", "fetchedAt": times.get(name, result["finishedAt"]), "errors": [f for f in result["failed"] if f.startswith(name + ":")]} for name, _ in SOURCES]
    atomic_json(OUT, result)
    print("%s: %d 源抓到, %d 源失败（%d 次失败尝试）" % (OUT.name, len(successful), len(SOURCES) - len(successful), len(result["failed"])))
    return 0 if not result["failed"] else 2


def main(argv=()):
    global OUT, SOURCES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=OUT)
    parser.add_argument("--sources", nargs="+", choices=SOURCE_URLS)
    args = parser.parse_args(argv)
    OUT = args.output
    if args.sources:
        SOURCES = [(name, SOURCE_URLS[name]) for name in dict.fromkeys(args.sources)]
    try:
        return run()
    except Exception as exc:
        # Browser driver startup/context shutdown can fail before normal finish.
        result = json.loads(OUT.read_text(encoding="utf-8"))
        successful = {s["source"] for s in result["snapshots"]}
        for name, _ in SOURCES:
            if name not in successful and not any(f.startswith(name + ":") for f in result["failed"]):
                result["failed"].append(f"{name}: browser startup/run failed ({type(exc).__name__})")
        return finish(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
