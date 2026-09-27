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

    // 云端不可达时（例如托管在 github.io，Origin 与云端应用的保留域名不一致），
    // 隐藏 AI 面板并把状态行改成静态版说明，避免看着像坏了。
    function degradeToStatic(reason) {{
      var ai = document.getElementById('aiPanel');
      if (ai) ai.style.display = 'none';
      var n = document.querySelectorAll('tbody tr').length;
      setSrcbar('off', '静态快照 ' + n + ' 条 · 每日由自动任务重建并发布' +
        (reason ? '（云端不可达：' + reason + '）' : ''));
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
        degradeToStatic('云端 SDK 未加载');
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
        degradeToStatic((err && err.message) ? err.message : '未知错误');
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