#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Playwright 无头浏览器抓三个 SPA 列表源（脚本直抓拿不到正文的那三个）。

输出 spa_snapshot.json：[{source, url, text}]，供 ai_update.py 的发现环节消费。
设计约束：
- 本地与 GitHub Actions runner 都能跑（依赖 playwright + chromium）；
- 单源失败不阻断（记入 failed）；
- Kaggle 必须用完整版 Chromium（channel="chromium" 新 headless 模式）过 Cloudflare，
  headless shell 会被卡在「正在检查浏览器」页。
"""
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "spa_snapshot.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

SOURCES = [
    ("kaggle", "https://www.kaggle.com/competitions"),
    ("tianchi", "https://tianchi.aliyun.com/competition/algorithmList"),
    ("xfyun", "https://challenge.xfyun.cn/"),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 未安装，跳过 SPA 抓取", file=sys.stderr)
        OUT.write_text("[]", encoding="utf-8")
        return 0
    snap, failed = [], []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chromium", headless=True,
                                        args=["--disable-blink-features=AutomationControlled"])
        except Exception:
            browser = p.chromium.launch(headless=True)  # 兜底：完整版不存在时用 shell
        for name, url in SOURCES:
            pg = None
            try:
                # Kaggle 的 Cloudflare 检查对 zh-CN 更严，英文站用 en-US context（实测通过）
                ctx = browser.new_context(
                    user_agent=UA, locale="en-US" if name == "kaggle" else "zh-CN",
                    viewport={"width": 1440, "height": 900})
                pg = ctx.new_page()
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                body = ""
                for _ in range(8):  # 最多等 40s：SPA 渲染 / Cloudflare 检查页自动跳转
                    pg.wait_for_timeout(5000)
                    body = pg.inner_text("body")
                    if ("检查浏览器" not in body and "Checking your browser" not in body
                            and len(body) > 500):
                        break
                if len(body) < 500:
                    failed.append(name + ": page still empty/check after 40s")
                else:
                    snap.append({"source": name, "url": url,
                                 "text": body[:12000]})  # 每源最多 12K 字符
            except Exception as e:
                failed.append("%s: %r" % (name, e))
            finally:
                if pg:
                    pg.close()
                ctx.close()
        browser.close()
    OUT.write_text(json.dumps({"snapshots": snap, "failed": failed}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("spa_snapshot.json: %d 源抓到, %d 失败 %s" % (len(snap), len(failed), failed or ""))


if __name__ == "__main__":
    sys.exit(main())
