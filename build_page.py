#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竞赛清单页面构建脚本（数据与外观分层，改版式只改这里）。

筛选模型：托管平台 / 所属会议 / 方向 / 截止窗口 四个维度 + 仅可新参加开关 + 排序。
chip 计数为分面计数（反映在其他维度当前选中条件下还剩多少），不是全量固定值。
"""
import json, pathlib, datetime, html, collections, re, os

BASE = pathlib.Path(__file__).resolve().parent
SRC = pathlib.Path(os.environ.get("EVENTS_DIR", str(BASE)))
OUT = pathlib.Path(os.environ.get("OUT_HTML", str(BASE / "index.html")))
ARCHIVE_JSON = pathlib.Path(os.environ.get("ARCHIVE_JSON", str(SRC / "archive.json")))

CLOUD = {
    "endpoint": "https://competition-scout.app.workbuddy.host",
    "publishableKey": "wbpk_REMOVED",
}

SHOW_SECTIONS = False
SHOW_ARCHIVE = False
SHOW_FOOTER = False

events = json.load(open(SRC / "events.json", encoding="utf-8"))
TODAY = datetime.date(2026, 9, 27)

PLAT_CLASS = {"Kaggle": "kaggle", "天池": "cn", "讯飞": "xf", "Devpost": "devpost", "会议官网": "conf"}


def plat_class(name):
    return PLAT_CLASS.get(name, "other")


TAGSLUG = {"CV": "cv", "大模型": "llm", "Agent": "agent", "检索 / RAG": "rag",
           "推荐 / 广告": "rec", "医学": "med", "3D": "3d", "多模态": "mm",
           "具身 / 机器人": "emb"}
TAGORDER = ["cv", "llm", "agent", "rag", "rec", "med", "3d", "mm", "emb"]
TAGLABEL = {v: k for k, v in TAGSLUG.items()}
STATUS = {
    "open": ("open", "可新参加", 0),
    "submission": ("submission", "仅已报名", 1),
    "unclear": ("unclear", "待确认", 2),
    "upcoming": ("upcoming", "待发布", 3),
    "practice": ("practice", "长期练习", 4),
    "closed": ("closed", "已结束", 5),
}
WINDOWS = [("w7", "7 天内"), ("w30", "8–30 天"), ("later", "30 天以上"), ("past", "已截止 / 无日期")]


def days_to(day):
    if not day:
        return None
    try:
        return (datetime.date.fromisoformat(day) - TODAY).days
    except ValueError:
        return None


def days_left(e):
    ds = [d for d in (days_to(e.get("entry", {}).get("day")), days_to(e.get("submit", {}).get("day")))
          if d is not None]
    fut = [d for d in ds if d >= 0]
    return min(fut) if fut else -1


DOMESTIC = {"天池", "讯飞", "百度", "DataFountain", "阿里云天池"}
_TZ_NOISE = [
    r"[；;，,]?\s*官网未写具体时刻\s*/\s*时区[。；;]?",
    r"[；;，,]?\s*官网未注明截止时刻\s*/\s*时区[。；;]?",
    r"[；;，,]?\s*官网未注明时刻\s*/\s*时区[。；;]?",
    r"[；;，,]?\s*官网未注明时区[。；;]?",
    r"[；;，,]?\s*官网未明确时区[。；;]?",
    r"[；;，,]?\s*官网未注时区[。；;]?",
    r"[；;，,]?\s*网站未注明时区[。；;]?",
    r"[；;，,]?\s*未注明时区[。；;]?",
]


def normalize_tz(text, domestic):
    if not text:
        return text
    if domestic:
        for p in _TZ_NOISE:
            text = re.sub(p, "", text)
        text = re.sub(r"[；;]{2,}", "；", text)
        text = re.sub(r"^[；;，,、\s]+", "", text)
        text = re.sub(r"[；;，,、\s]+$", "", text)
        text = text.strip("。 ")
        if not text:
            return "—"
    return text


def sortkey(e):
    w = STATUS.get(e["status"], ("closed", "", 9))[2]
    d = days_left(e)
    return (w, e.get("priority", 9), d if d >= 0 else 99999)


events = sorted(events, key=sortkey)

n_all = len(events)
n_open = sum(1 for e in events if e["status"] == "open")
n_week = sum(1 for e in events if e["status"] in ("open", "submission") and 0 <= days_left(e) <= 7)
n_pending = sum(1 for e in events if e["status"] in ("unclear", "upcoming"))
n_plat = len({e["platform"] for e in events})
n_venue = len({e["venue"] for e in events if e["venue"]})

NO_VENUE = "__none__"          # 无会议归属的哨兵值：chip 的 data-f 与行的 data-venue 必须用同一个值
VENUE_LABEL = {NO_VENUE: "平台自办赛"}

plat_count = collections.Counter(e["platform"] for e in events)
venue_count = collections.Counter(e["venue"] or NO_VENUE for e in events)
tag_count = collections.Counter(TAGSLUG[t] for e in events for t in e["tags"] if t in TAGSLUG)
win_count = collections.Counter(
    "w7" if 0 <= days_left(e) <= 7 else
    "w30" if 7 < days_left(e) <= 30 else
    "later" if days_left(e) > 30 else "past" for e in events)

venue_order = sorted(venue_count, key=lambda v: (-venue_count[v], v))
plat_order = sorted(plat_count, key=lambda v: (-plat_count[v], v))


def chip_html(dim, value, label, count, on=False):
    return ('<button class="chip%s" data-dim="%s" data-f="%s">%s<span class="cnt">%d</span></button>'
            % (" on" if on else "", dim, html.escape(value), html.escape(label), count))


def chips(dim, items, order=None, labels=None):
    labels = labels or {}
    if dim == "tag":
        pairs = [(s, TAGLABEL[s]) for s in TAGORDER if items.get(s)]
    elif dim == "win":
        pairs = list(WINDOWS)
    else:
        pairs = [(k, labels.get(k, k)) for k in (order or sorted(items))]
    out = [chip_html(dim, "all", "全部", sum(items.values()), on=True)]
    out += [chip_html(dim, k, lbl, items.get(k, 0)) for k, lbl in pairs]
    return "\n    ".join(out)


def row(e):
    st, st_label, _ = STATUS.get(e["status"], ("closed", e["status"], 9))
    domestic = e["platform"] in DOMESTIC
    times = []
    for label, key in (("报名", "entry"), ("提交", "submit")):
        node = e.get(key) or {}
        txt = normalize_tz(node.get("text") or "—", domestic)
        times.append('<div class="tline"><span class="tlabel">%s</span>%s</div>' % (label, html.escape(txt)))
    warn_txt = normalize_tz(e.get("warning") or "", domestic)
    if warn_txt and warn_txt != "—" and not re.search(r"[。！？…”》]$", warn_txt):
        warn_txt += "。"
    warn = '<div class="warn">%s</div>' % html.escape(warn_txt) if warn_txt else ""
    tags = "".join('<span class="cat">%s</span>' % html.escape(t) for t in e["tags"])
    tag_slugs = " ".join(TAGSLUG.get(t, "other") for t in e["tags"])
    venue = e["venue"]
    venue_attr = venue or NO_VENUE
    venue_pill = ('<span class="cat venue">%s</span>' % html.escape(venue)) if venue else ""
    vby = e.get("verifiedBy") or "human"
    return """      <tr data-id="{eid}" data-status="{st}" data-plat="{plat}" data-venue="{venue}" data-tag="{tags_s}"
          data-days="{days}" data-pri="{pri}" data-vby="{vby}">
        <td class="c-name"><a href="{url}" target="_blank" rel="noopener">{title}</a><span class="st {st}">{stlabel}</span>
          <div class="tagrow"><span class="cat {pcls}">{plat}</span>{venue_pill}<span class="pri">P{pri}</span></div>
          <div class="tagrow">{tags}</div></td>
        <td class="c-dir">{task}</td>
        <td class="c-time">{times}{warn}</td>
        <td class="c-req">{req}</td>
        <td class="c-prize">{award}</td>
      </tr>""".format(
        eid=html.escape(e["id"]), vby=vby,
        st=st, plat=html.escape(e["platform"]), pcls=plat_class(e["platform"]),
        venue=html.escape(venue_attr), venue_pill=venue_pill,
        tags_s=tag_slugs, days=days_left(e), pri=e.get("priority", 9),
        url=e["url"], title=html.escape(e["title"]), stlabel=st_label, tags=tags,
        task=html.escape(e["task"]), times="".join(times), warn=warn,
        req=html.escape(e["requirements"]), award=html.escape(e["award"]))


render_rows = []
for i, e in enumerate(events):
    r = row(e)
    r = r.replace('data-pri="%s">' % e.get("priority", 9),
                  'data-pri="%s" data-ord="%d">' % (e.get("priority", 9), i), 1)
    render_rows.append(r)
render_rows = "\n".join(render_rows)

CSS = """  :root{
    --bg:#ffffff; --bg2:#f7f7f5; --line:rgba(0,0,0,.12); --line2:rgba(0,0,0,.06);
    --t1:#2c2c2a; --t2:#5f5e5a; --t3:#888780;
    --purple-f:#cecbf6; --purple-t:#3c3489;
    --blue-f:#b5d4f4; --blue-t:#0c447c;
    --amber-f:#fac775; --amber-t:#633806;
    --teal-f:#9fe1cb; --teal-t:#085041;
    --grass-f:#c0dd97; --grass-t:#27500a;
    --red-t:#a32d2d; --red-f:#fcebeb;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg2);color:var(--t1);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:40px 24px 72px}
  h1{font-size:24px;font-weight:500;margin:0 0 8px}
  .sub{color:var(--t2);font-size:13px;margin:0 0 4px}
  .hint{color:var(--t3);font-size:12px;margin:0 0 28px}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:28px}
  .stat{background:var(--bg);border:1px solid var(--line2);border-radius:12px;padding:14px 16px}
  .stat .k{font-size:12px;color:var(--t2);margin:0 0 4px}
  .stat .v{font-size:22px;font-weight:500;margin:0;line-height:1.25}
  .stat .n{font-size:12px;color:var(--t3);margin:4px 0 0}
  .filters{background:var(--bg);border:1px solid var(--line2);border-radius:12px;padding:16px 18px;margin-bottom:16px}
  .frow{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .frow+.frow{margin-top:10px}
  .chiplabel{font-size:12px;color:var(--t3);min-width:52px;flex:0 0 auto}
  .chip{appearance:none;border:1px solid var(--line);background:var(--bg);color:var(--t2);
    border-radius:999px;padding:5px 13px;font-size:13px;cursor:pointer;font-family:inherit}
  .chip:hover{background:#f2f2ef}
  .chip.on{background:var(--t1);color:#fff;border-color:var(--t1)}
  .chip.disabled{opacity:.38;cursor:default}
  .chip.disabled:hover{background:var(--bg)}
  .cnt{font-size:11px;color:var(--t3);margin-left:5px}
  .chip.on .cnt{color:rgba(255,255,255,.72)}
  .chipsep{width:1px;height:22px;background:var(--line);align-self:center;margin:0 2px}
  .chip.toggle{border-style:dashed}
  .chip.toggle.on{background:#3b6d11;border-color:#3b6d11;border-style:solid;color:#fff}
  .fbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px;
    padding-top:12px;border-top:1px solid var(--line2)}
  .fbar select{font-family:inherit;font-size:13px}
  .btn{appearance:none;border:1px solid var(--line);background:var(--bg);color:var(--t2);
    border-radius:8px;padding:5px 12px;font-size:13px;cursor:pointer;font-family:inherit}
  .btn:hover{background:#f2f2ef}
  .visline{font-size:12px;color:var(--t3);margin:0 0 14px}
  .visline b{font-weight:500;color:var(--t1)}
  .card{background:var(--bg);border:1px solid var(--line2);border-radius:12px;overflow:hidden}
  table{width:100%;border-collapse:collapse;table-layout:fixed}
  thead th{text-align:left;font-weight:500;font-size:12px;color:var(--t2);
    padding:12px 14px;border-bottom:1px solid var(--line);background:#fbfbfa;white-space:nowrap}
  tbody td{padding:14px;border-bottom:1px solid var(--line2);vertical-align:top;font-size:13px}
  tbody tr:last-child td{border-bottom:0}
  tbody tr:hover{background:#fbfbfa}
  .c-name{width:21%}
  .c-dir{width:19%}
  .c-time{width:23%}
  .c-req{width:21%}
  .c-prize{width:16%}
  a{color:var(--blue-t);text-decoration:none;border-bottom:1px solid rgba(12,68,124,.28)}
  a:hover{border-bottom-color:var(--blue-t)}
  .cat{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;white-space:nowrap;
    background:var(--bg2);color:var(--t2);border:1px solid var(--line2);margin-right:4px}
  .cat.kaggle{background:var(--blue-f);color:var(--blue-t);border-color:transparent}
  .cat.cn{background:var(--amber-f);color:var(--amber-t);border-color:transparent}
  .cat.xf{background:var(--teal-f);color:var(--teal-t);border-color:transparent}
  .cat.conf{background:var(--purple-f);color:var(--purple-t);border-color:transparent}
  .cat.venue{background:var(--grass-f);color:var(--grass-t);border-color:transparent}
  .cat.devpost,.cat.other{background:var(--bg2);color:var(--t1);border-color:var(--line)}
  .pri{display:inline-block;font-size:11px;color:var(--t3)}
  .tagrow{margin-top:6px}
  .st{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;margin-left:6px;white-space:nowrap;vertical-align:1px}
  .st.open{background:#eaf3de;color:#3b6d11}
  .st.submission{background:#e6f1fb;color:#185fa5}
  .st.unclear{background:#fbfbfa;color:#888780;border:1px solid var(--line2)}
  .st.upcoming{background:#faeeda;color:#854f0b}
  .st.practice{background:#e1f5ee;color:#0f6e56}
  .st.closed{background:#f1efe8;color:#5f5e5a}
  .now{color:var(--red-t);font-weight:500}
  .tline{margin-bottom:3px}
  .tlabel{display:inline-block;min-width:26px;color:var(--t3);font-size:11px}
  .warn{margin-top:8px;padding:6px 9px;background:var(--red-f);border-left:2px solid #e24b4a;
    border-radius:4px;font-size:12px;color:var(--red-t);line-height:1.5}
  tr[data-status="closed"] .c-name a{color:var(--t3);border-bottom-color:var(--line2)}
  tr[data-status="closed"] .c-dir,tr[data-status="closed"] .c-time,
  tr[data-status="closed"] .c-req,tr[data-status="closed"] .c-prize{color:var(--t3)}
  tr[data-status="closed"] .c-time .now{color:var(--red-t)}
  .empty{display:none;padding:40px;text-align:center;color:var(--t3);font-size:13px}
  .vb{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;margin-left:4px;white-space:nowrap;vertical-align:1px}
  .vb.auto{background:#faeeda;color:#854f0b}
  .srcbar{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:12px;color:var(--t3);
    margin:0 0 14px}
  .srcbar .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:1px}
  .srcbar .dot.ok{background:#639922}
  .srcbar .dot.warn{background:#ba7517}
  .srcbar .dot.off{background:#b4b2a9}
  .ai{background:var(--bg);border:1px solid var(--line2);border-radius:12px;padding:14px 18px;margin-bottom:16px}
  .ai .hd{font-size:13px;font-weight:500;margin:0 0 8px}
  .ai .row{display:flex;gap:8px;align-items:center}
  .ai input{flex:1 1 auto;min-width:0;font-family:inherit;font-size:13px;padding:7px 11px}
  .ai .hintline{font-size:12px;color:var(--t3);margin:8px 0 0}
  .ai .ans{display:none;margin:10px 0 0;padding:10px 12px;background:var(--bg2);
    border-radius:8px;font-size:13px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
  .ai .ans.on{display:block}
  .ai .ans.err{background:var(--red-f);color:var(--red-t)}
  .muted{color:var(--t3)}
  h2{font-size:16px;font-weight:500;margin:40px 0 12px}
  ul{margin:0;padding-left:20px;color:var(--t1)}
  ul.tight{padding-left:18px}
  li{margin-bottom:8px}
  ul.tight li{margin-bottom:4px}
  li b{font-weight:500}
  .note{background:var(--bg);border:1px solid var(--line2);border-radius:12px;padding:18px 22px}
  .note p{margin:0 0 10px}
  .note p:last-child{margin-bottom:0}
  .grouphd{font-weight:500;margin:14px 0 6px !important;color:var(--t2);font-size:13px}
  @media (max-width:760px){
    table,thead,tbody,tr,td,th{display:block}
    thead{display:none}
    tbody tr{border-bottom:1px solid var(--line);padding:12px 0}
    tbody td{border:0;padding:3px 14px}
    .c-name,.c-dir,.c-time,.c-req,.c-prize{width:auto}
    .chiplabel{min-width:100%}
  }"""

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CV / 大模型 / 搜广推 竞赛清单 · {today}</title>
<style>
{css}
</style>
</head>
<body>
<div class="wrap">

  <h1>CV / 大模型 / 搜广推 竞赛清单</h1>
  <p class="sub">逐条核对官方来源后确认还能参加的具体赛题。托管平台与所属会议分开标注，报名资格、提交要求与截止时间分别列出。</p>
  <p class="hint">核验日期 <b>{today}</b> · 已启用非学生身份筛选 · 每条均附官方入口。竞赛时间与奖金常变动，报名前请以官网为准。<br>时区口径：<b>国内赛事（天池 / 讯飞 等）按北京时间 GMT+8</b>；海外赛事保留官网原始时区，并附北京时间换算。</p>

  <div class="stats">
    <div class="stat"><p class="k">已核验具体条目</p><p class="v">{n_all}</p><p class="n">逐条核对官方来源</p></div>
    <div class="stat"><p class="k">可新参加</p><p class="v">{n_open}</p><p class="n">未发现已过的强制前置节点</p></div>
    <div class="stat"><p class="k">7 天内行动截止</p><p class="v">{n_week}</p><p class="n">仅计可新参加 / 仅已报名</p></div>
    <div class="stat"><p class="k">待确认 / 待发布</p><p class="v">{n_pending}</p><p class="n">身份资格或日期不明</p></div>
    <div class="stat"><p class="k">覆盖托管平台</p><p class="v">{n_plat}</p><p class="n">另有 {n_venue} 个所属会议</p></div>
  </div>

  <p class="srcbar" id="srcbar"><span><span class="dot off"></span>正在连接云端…</span></p>

  <div class="filters">
    <div class="frow"><span class="chiplabel">托管平台</span>
    {chips_plat}
    </div>
    <div class="frow"><span class="chiplabel">所属会议</span>
    {chips_venue}
    </div>
    <div class="frow"><span class="chiplabel">方向</span>
    {chips_tag}
    </div>
    <div class="frow"><span class="chiplabel">截止窗口</span>
    {chips_win}
    </div>
    <div class="frow"><span class="chiplabel">其他</span>
    <button class="chip toggle" id="liveToggle">仅可新参加</button>
    <button class="btn" id="resetBtn">重置全部</button>
    </div>
    <div class="fbar">
      <label class="chiplabel" for="sortSel" style="min-width:auto">排序</label>
      <select id="sortSel">
        <option value="default">推荐排序（状态 → 优先级 → 最近截止）</option>
        <option value="deadline">截止日最近优先</option>
        <option value="priority">优先级 P1 → P5</option>
      </select>
      <span class="visline" style="margin:0 0 0 6px">当前显示 <b id="visCount">{n_all}</b> / {n_all} 条<span id="hiddenNote"></span></span>
    </div>
  </div>

  <div class="ai" id="aiPanel">
    <p class="hd">用自然语言筛选</p>
    <div class="row">
      <input id="aiInput" type="text" placeholder="例如：医学影像相关、两周内截止、非学生才能报的有哪些？" autocomplete="off">
      <button class="btn" id="aiBtn">问 AI</button>
      <button class="btn" id="aiStop" style="display:none">停止</button>
    </div>
    <p class="hintline">只把当前筛选出的条目（最多 40 条）发给模型，不会上传完整数据。回答仅供参考，报名前请以官网为准。</p>
    <div class="ans" id="aiAns"></div>
  </div>

  <div class="card">
  <table>
    <thead>
      <tr>
        <th class="c-name">赛事</th>
        <th class="c-dir">任务</th>
        <th class="c-time">报名 · 提交</th>
        <th class="c-req">资格 · 提交要求</th>
        <th class="c-prize">奖金 · 权益</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p class="empty" id="emptyMsg">没有符合当前组合条件的赛事，试试放宽筛选或点「重置全部」。</p>
  </div>

{sections}{footer}
</div>

<script src="https://cdn.jsdelivr.net/npm/@tencent-ai/workbuddy-cloud-sdk@dev/lib/index.global.js"></script>
<script>
  (function () {{
    var rows = null;
    function refreshRows() {{ rows = [].slice.call(document.querySelectorAll('tbody tr')); }}
    refreshRows();
    var tbody = document.querySelector('tbody');
    var state = {{ venue: 'all', plat: 'all', tag: 'all', win: 'all', live: false, sort: 'default' }};
    var visCount = document.getElementById('visCount');
    var hiddenNote = document.getElementById('hiddenNote');
    var emptyMsg = document.getElementById('emptyMsg');
    var toggle = document.getElementById('liveToggle');
    var cloud = null;
    var modelId = null;
    var DIMS = ['venue', 'plat', 'tag', 'win'];
    var groups = {{}};
    DIMS.forEach(function (d) {{
      groups[d] = [].slice.call(document.querySelectorAll('.chip[data-dim="' + d + '"]'));
    }});

    function vals(tr, dim) {{
      if (dim === 'tag') return (tr.getAttribute('data-tag') || '').split(' ');
      return [tr.getAttribute('data-' + dim) || ''];
    }}

    function winOk(days, w) {{
      var d = parseFloat(days);
      if (isNaN(d)) return false;
      if (w === 'w7') return d >= 0 && d <= 7;
      if (w === 'w30') return d > 7 && d <= 30;
      if (w === 'later') return d > 30;
      if (w === 'past') return d < 0;
      return true;
    }}

    function hit(tr, dim, f) {{
      var v = vals(tr, dim);
      if (dim === 'win') return winOk(tr.getAttribute('data-days'), f);
      return v.indexOf(f) >= 0;
    }}

    function match(tr, skipDim, override) {{
      override = override || {{}};
      for (var i = 0; i < DIMS.length; i++) {{
        var dim = DIMS[i];
        if (dim === skipDim) continue;
        var sel = (dim in override) ? override[dim] : state[dim];
        if (sel === 'all') continue;
        if (!hit(tr, dim, sel)) return false;
      }}
      if (state.live && tr.getAttribute('data-status') !== 'open') return false;
      return true;
    }}

    function faceted() {{
      DIMS.forEach(function (dim) {{
        groups[dim].forEach(function (btn) {{
          var f = btn.getAttribute('data-f');
          var n = 0;
          for (var i = 0; i < rows.length; i++) {{
            var tr = rows[i];
            if (!match(tr, dim, {{}})) continue;
            if (f === 'all' || hit(tr, dim, f)) n++;
          }}
          var c = btn.querySelector('.cnt');
          if (c) c.textContent = n;
          btn.classList.toggle('disabled', n === 0 && !btn.classList.contains('on'));
        }});
      }});
    }}

    function dk(tr) {{ var d = parseInt(tr.getAttribute('data-days'), 10); return d < 0 ? 99999 : d; }}
    function pk(tr) {{ return parseInt(tr.getAttribute('data-pri'), 10); }}

    function sortRows(mode) {{
      var arr = rows.slice();
      if (mode === 'deadline') arr.sort(function (a, b) {{ return dk(a) - dk(b) || pk(a) - pk(b); }});
      else if (mode === 'priority') arr.sort(function (a, b) {{ return pk(a) - pk(b) || dk(a) - dk(b); }});
      else arr.sort(function (a, b) {{
        return parseInt(a.getAttribute('data-ord'), 10) - parseInt(b.getAttribute('data-ord'), 10);
      }});
      arr.forEach(function (tr) {{ tbody.appendChild(tr); }});
    }}

    function apply() {{
      var shown = 0;
      rows.forEach(function (tr) {{
        var ok = match(tr, null, {{}});
        tr.style.display = ok ? '' : 'none';
        if (ok) shown++;
      }});
      visCount.textContent = shown;
      hiddenNote.textContent = shown < rows.length ? '（已隐藏 ' + (rows.length - shown) + ' 条）' : '';
      emptyMsg.style.display = shown === 0 ? 'block' : 'none';
      faceted();
      sortRows(state.sort);
    }}

    DIMS.forEach(function (dim) {{
      groups[dim].forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          if (btn.classList.contains('disabled') && !btn.classList.contains('on')) return;
          groups[dim].forEach(function (b) {{ b.classList.toggle('on', b === btn); }});
          state[dim] = btn.getAttribute('data-f');
          apply();
        }});
      }});
    }});

    toggle.addEventListener('click', function () {{
      state.live = !state.live;
      toggle.classList.toggle('on', state.live);
      apply();
    }});

    document.getElementById('sortSel').addEventListener('change', function (e) {{
      state.sort = e.target.value;
      apply();
    }});

    document.getElementById('resetBtn').addEventListener('click', function () {{
      DIMS.forEach(function (dim) {{
        state[dim] = 'all';
        groups[dim].forEach(function (b) {{ b.classList.toggle('on', b.getAttribute('data-f') === 'all'); }});
      }});
      state.live = false;
      toggle.classList.remove('on');
      state.sort = 'default';
      document.getElementById('sortSel').value = 'default';
      apply();
    }});

    apply();

    // ================= 云端覆盖层 =================
    var STATUS_LABEL = {{
      open: '可新参加', submission: '仅已报名', unclear: '待确认',
      upcoming: '待发布', practice: '长期练习', closed: '已结束'
    }};
    var TAG_SLUG = {{
      'CV': 'cv', '大模型': 'llm', 'Agent': 'agent', '检索 / RAG': 'rag',
      '推荐 / 广告': 'rec', '医学': 'med', '3D': '3d', '多模态': 'mm', '具身 / 机器人': 'emb'
    }};
    var PLAT_CLS = {{ Kaggle: 'kaggle', '天池': 'cn', '讯飞': 'xf', Devpost: 'devpost', '会议官网': 'conf' }};
    var TODAY = new Date('{today}T00:00:00+08:00');

    function esc(t) {{
      return (t === null || t === undefined) ? '' : String(t)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }}

    function daysLeft(e) {{
      var out = [];
      [e.entry_day, e.submit_day].forEach(function (d) {{
        if (!d) return;
        var t = new Date(String(d).slice(0, 10) + 'T00:00:00+08:00');
        if (isNaN(t)) return;
        var n = Math.round((t - TODAY) / 86400000);
        if (n >= 0) out.push(n);
      }});
      return out.length ? Math.min.apply(null, out) : -1;
    }}

    function renderRow(e) {{
      var st = e.status || 'open';
      var stLabel = STATUS_LABEL[st] || st;
      var tags = (e.tags || []);
      var tagHtml = tags.map(function (t) {{ return '<span class="cat">' + esc(t) + '</span>'; }}).join('');
      var tagSlugs = tags.map(function (t) {{ return TAG_SLUG[t] || 'other'; }}).join(' ');
      var venuePill = e.venue ? '<span class="cat venue">' + esc(e.venue) + '</span>' : '';
      var warn = e.warning
        ? '<div class="warn">' + esc(e.warning) + '</div>' : '';
      var vby = e.verified_by || 'human';
      var vbyBadge = vby === 'auto'
        ? '<span class="vb auto">系统推算</span>' : '';
      return '<tr data-id="' + esc(e.id) + '" data-status="' + st + '" data-plat="' + esc(e.platform || '') +
        '" data-venue="' + esc(e.venue || '__none__') + '" data-tag="' + tagSlugs +
        '" data-days="' + daysLeft(e) + '" data-pri="' + (e.priority || 9) + '" data-ord="9999" data-vby="' + vby + '">' +
        '<td class="c-name"><a href="' + esc(e.url) + '" target="_blank" rel="noopener">' + esc(e.title) +
        '</a><span class="st ' + st + '">' + stLabel + '</span>' + vbyBadge +
        '<div class="tagrow"><span class="cat ' + (PLAT_CLS[e.platform] || 'other') + '">' + esc(e.platform) +
        '</span>' + venuePill + '<span class="pri">P' + (e.priority || '') + '</span></div>' +
        '<div class="tagrow">' + tagHtml + '</div></td>' +
        '<td class="c-dir">' + esc(e.task) + '</td>' +
        '<td class="c-time"><div class="tline"><span class="tlabel">报名</span>' + esc(e.entry_text) +
        '</div><div class="tline"><span class="tlabel">提交</span>' + esc(e.submit_text) + '</div>' + warn + '</td>' +
        '<td class="c-req">' + esc(e.requirements) + '</td>' +
        '<td class="c-prize">' + esc(e.award) + '</td></tr>';
    }}

    function applyOverlay(list) {{
      var tb = document.querySelector('tbody');
      var byId = {{}};
      list.forEach(function (r) {{ byId[r.id] = r; }});
      var patched = 0, added = 0;
      [].slice.call(tb.querySelectorAll('tr')).forEach(function (tr) {{
        var id = tr.getAttribute('data-id');
        var r = byId[id];
        if (!r) return;
        delete byId[id];
        if (r.status === 'removed') {{ tr.remove(); patched++; return; }}
        tr.outerHTML = renderRow(r);
        patched++;
      }});
      var tail = [];
      Object.keys(byId).forEach(function (id) {{
        var r = byId[id];
        if (r.status === 'removed') return;
        tail.push(renderRow(r));
        added++;
      }});
      if (tail.length) tb.insertAdjacentHTML('beforeend', tail.join(''));
      refreshRows();
      apply();
      return {{ patched: patched, added: added }};
    }}

    function setSrcbar(dotCls, text) {{
      var bar = document.getElementById('srcbar');
      bar.innerHTML = '<span><span class="dot ' + dotCls + '"></span>' + esc(text) + '</span>';
    }}

    function bjTime(iso) {{
      var d = new Date(iso);
      if (isNaN(d)) return String(iso).slice(0, 16).replace('T', ' ');
      var bj = new Date(d.getTime() + 8 * 3600 * 1000), p = function (n) {{ return (n < 10 ? '0' : '') + n; }};
      return bj.getUTCFullYear() + '-' + p(bj.getUTCMonth() + 1) + '-' + p(bj.getUTCDate()) +
        ' ' + p(bj.getUTCHours()) + ':' + p(bj.getUTCMinutes());
    }}

    function boot() {{
      var base = document.querySelectorAll('tbody tr').length;
      if (!window.WorkBuddyCloud) {{
        setSrcbar('off', '本地基线快照 ' + base + ' 条（云端 SDK 未加载，可能离线）');
        return;
      }}
      cloud = WorkBuddyCloud.createWorkBuddyCloud({{
        endpoint: '{endpoint}',
        publishableKey: '{publishableKey}'
      }});
      cloud.database.from('events').select('*').then(function (res) {{
        if (res.error) throw res.error;
        var st = applyOverlay(res.data || []);
        return cloud.database.from('runs').select('*')
          .order('run_at', {{ ascending: false }}).limit(1)
          .then(function (r2) {{ return {{ st: st, run: (r2.data || [])[0], base: base }}; }});
      }}).then(function (o) {{
        var fresh = o.run && o.run.run_at
          ? '上次自动运行 ' + bjTime(o.run.run_at) + '（北京）'
          : '尚无自动运行记录';
        setSrcbar(o.run && o.run.ok === false ? 'warn' : 'ok',
          '云端已连接 · 基线 ' + o.base + ' 条 + 覆盖 ' + (o.st.patched + o.st.added) + ' 条（' + fresh + '）');
      }}).catch(function (err) {{
        setSrcbar('warn', '云端读取失败，当前显示本地基线快照 ' + base + ' 条：' +
          ((err && err.message) ? err.message : '未知错误'));
      }});
    }}

    boot();

    // ================= 站内 AI 问答 =================
    var AI_SYS = '你是一个竞赛信息助手。用户会给你一份竞赛条目清单（含平台、方向、状态、截止说明、资格要求）'
      + '和一个问题。只依据清单内容作答，不要编造清单之外的赛事或日期。'
      + '用简体中文、条目式回答，每条给出赛事名 + 关键时间 + 为什么符合；'
      + '如果清单里没有符合条件的，直接说没有，不要勉强凑数。';

    var aiInput = document.getElementById('aiInput');
    var aiBtn = document.getElementById('aiBtn');
    var aiStop = document.getElementById('aiStop');
    var aiAns = document.getElementById('aiAns');
    var aiCtrl = null;

    function trToLine(tr) {{
      var g = function (k) {{ return tr.getAttribute(k) || ''; }};
      var name = (tr.querySelector('.c-name a') || {{}}).textContent || '';
      var cells = tr.querySelectorAll('td');
      var time = cells[2] ? cells[2].innerText.replace(/\\s+/g, ' ').trim() : '';
      var req = cells[3] ? cells[3].innerText.replace(/\\s+/g, ' ').trim() : '';
      var status = (tr.querySelector('.st') || {{}}).textContent || '';
      var vby = g('data-vby');
      return '- ' + name + '｜平台:' + g('data-plat') + '｜会议:' + (g('data-venue') === '__none__' ? '无' : g('data-venue'))
        + '｜方向:' + g('data-tag') + '｜状态:' + status + (vby === 'auto' ? '(系统推算)' : '(已核验)')
        + '｜时间:' + time + '｜要求:' + req;
    }}

    function setAi(msg, isErr) {{
      aiAns.textContent = msg;
      aiAns.className = 'ans on' + (isErr ? ' err' : '');
    }}

    async function ask() {{
      var q = aiInput.value.trim();
      if (!q) return;
      if (!cloud) {{ setAi('云端未连接，暂时无法使用 AI 问答。', true); return; }}
      var list = rows.filter(function (tr) {{ return tr.style.display !== 'none'; }});
      if (!list.length) {{ setAi('当前筛选结果为空，先放宽条件再问。', true); return; }}
      var ctx = list.slice(0, 40).map(trToLine).join('\\n');
      var extra = list.length > 40 ? '\\n(共 ' + list.length + ' 条，只发送了前 40 条)' : '';

      aiBtn.disabled = true;
      aiStop.style.display = '';
      setAi('思考中…', false);

      try {{
        if (!modelId) {{
          var models = await cloud.llm.models.list();
          if (!models || !models.length) {{ setAi('当前没有可用模型，稍后再试。', true); return; }}
          var m = models.find(function (x) {{ return x.disabled !== true; }});
          if (!m) {{ setAi('当前没有可用模型，稍后再试。', true); return; }}
          modelId = m.id;
        }}
        aiCtrl = new AbortController();
        var out = '';
        for await (var chunk of cloud.llm.chat.completions.create({{
          model: modelId,
          messages: [
            {{ role: 'system', content: AI_SYS }},
            {{ role: 'user', content: '清单：\\n' + ctx + extra + '\\n\\n问题：' + q }}
          ],
          stream: true,
          signal: aiCtrl.signal
        }})) {{
          var d = chunk.choices && chunk.choices[0] && chunk.choices[0].delta;
          if (d && d.content) {{ out += d.content; setAi(out, false); }}
        }}
        if (!out) setAi('模型没有返回内容，换个问法试试。', true);
      }} catch (err) {{
        var msg = (err && err.error && err.error.message) || (err && err.message) || '未知错误';
        setAi('AI 调用失败：' + msg, true);
      }} finally {{
        aiBtn.disabled = false;
        aiStop.style.display = 'none';
        aiCtrl = null;
      }}
    }}

    aiBtn.addEventListener('click', ask);
    aiInput.addEventListener('keydown', function (ev) {{ if (ev.key === 'Enter') ask(); }});
    aiStop.addEventListener('click', function () {{ if (aiCtrl) aiCtrl.abort(); }});
  }})();
</script>
</body>
</html>
"""

sections = ""
footer = ""

out = HTML.format(
    today=TODAY.isoformat(), css=CSS, rows=render_rows,
    endpoint=CLOUD["endpoint"], publishableKey=CLOUD["publishableKey"],
    n_all=n_all, n_open=n_open, n_week=n_week, n_pending=n_pending,
    n_plat=n_plat, n_venue=n_venue,
    chips_plat=chips("plat", plat_count, plat_order),
    chips_venue=chips("venue", venue_count, venue_order, VENUE_LABEL),
    chips_tag=chips("tag", tag_count),
    chips_win=chips("win", win_count),
    sections=sections, footer=footer,
)
OUT.write_text(out, encoding="utf-8")
print("written:", OUT)
print("条目 %d · 可新参加 %d · 7 天内 %d · 待确认 %d" % (n_all, n_open, n_week, n_pending))
print("平台:", dict(plat_count))
print("会议:", dict(venue_count))
print("窗口:", dict(win_count))
