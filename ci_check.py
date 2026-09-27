#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建自检（CI 与本地共用）：结构校验 + 渲染后行数一致性。

校验点：
1. index.html 的 <tr data-id> 行数 == events.json 条目数；
2. id 无重复；
3. 页面数据截至日期 == BUILD_TODAY（默认今天）；
4. 基础 HTML 结构完整（table/tbody/script 闭合）。
"""
import json
import datetime
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent
today = datetime.date.fromisoformat(
    __import__("os").environ.get("BUILD_TODAY", datetime.date.today().isoformat())
).isoformat()

ok = True
events = json.loads((BASE / "events.json").read_text(encoding="utf-8"))
html = (BASE / "index.html").read_text(encoding="utf-8")

ids = [e["id"] for e in events]
if len(ids) != len(set(ids)):
    dup = [i for i in set(ids) if ids.count(i) > 1]
    print("FAIL: events.json 存在重复 id:", dup)
    ok = False

rows = len(re.findall(r"<tr data-id=", html))  # 页面无模板行，每行对应一条赛事
if rows != len(events):
    print("FAIL: 页面行数 %d != 条目数 %d" % (rows, len(events)))
    ok = False

if today not in html:
    print("FAIL: 页面未见数据截至日期 %s" % today)
    ok = False

for tag in ("</table>", "</tbody>", "</script>"):
    if html.count(tag) == 0:
        print("FAIL: 缺少 %s" % tag)
        ok = False

if ok:
    print("PASS: %d 条，页面行数一致，结构完整，数据截至 %s" % (len(events), today))
sys.exit(0 if ok else 1)
