# Competition Scout

通过仓库内的 Agent Skill 发现与核验 AI 竞赛，本地生成静态页面，再由所有者手动发布。

**已取消 GitHub Actions 自动刷新和代码检查任务。** 不再按每天 08:20 自动调用 GLM。Skill、Python Agent、数据和测试保留，可按需在本地运行。

## 页面与源码

源码仓库设为私有，公开页面仍为 https://shayne-pro.github.io/competition-scout/ 。GitHub Pages 使用 `main /docs`，只发布 `docs/index.html` 与 `.nojekyll`。Python 脚本、原始 JSON、Skill 和运行记录均不在发布目录；`ci_check.py` 拒绝发布目录出现其他文件或符号链接。

私有仓库的公开 Pages 需要 GitHub Pro 或支持的更高套餐。Pages 自身的系统部署仍会显示在 Actions 中，这是 GitHub 的内置发布机制；仓库没有自定义 Actions 工作流和定时任务。参见 [GitHub 官方说明](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。浏览器需要下载页面的 HTML/CSS/JavaScript，因此最终网页自身的前端代码可被查看。

## 本地更新

Python 3.9+。执行层是轻量 Python 工具调用循环，不依赖 OpenCode 或额外 Agent 框架；Playwright 只用于动态网页的浏览器回退。

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 scout.py prepare
# 从本机安全环境提供 LLM_API_KEY，可选 LLM_BASE_URL、LLM_MODEL；不要写进仓库。
python3 agent_refresh.py
python3 scout.py apply
python3 daily_refresh.py
python3 build_page.py
python3 ci_check.py
```

检查生成的 `docs/index.html` 和数据变化，确认后手动提交并推送 main。GitHub Pages 会更新页面；本地核验脚本不会自动提交或推送。原根目录 `index.html` 是迁移前快照，不再是发布源。

`ai_update.py` 是 prepare → Agent → apply 的兼容入口；`daily_refresh.py` 只计算已核实日期和记录提醒候选，不是定时任务，也不会发送消息。

## 核验与数据规则

- `scout.py prepare` 读取 `sources.json`，生成到期来源和最多 20 条复核目标。失败条目按上次尝试时间轮转，待确认与历史关闭条目可重新核验。
- Agent 只可读取任务、抓公开网页、记录来源、赛事和失败结果。没有 shell、任意文件读写或 Git 工具；网页正文是证据，不是操作指令。
- 提案先验证本轮 ID、原数据指纹、来源/目标覆盖、赛事身份、日期、资格和实际抓取的引用，再合并。未知日期清空旧值，学生专属赛事保留为 excluded 并从页面隐藏。
- 模型未产生有效提案时保留已有事件数据。历史和未完成项保留原状态，不将页面构建日期冒充全表核验日期。
- 新核验时间以带时区的 ISO 时间保存到秒，页面显示 `YYYY-MM-DD HH:mm:ss（北京时间）`。历史只有日期的记录保留原精度。

每轮最多 100 次模型轮次、180 次工具调用、65 次网页抓取，Agent 时间预算 20 分钟。可通过环境变量 `AGENT_MAX_STEPS` 降低模型轮次，准备队列时可使用 `scout.py prepare --limit 2`；单请求最多重试一次。

**API 配置：** 默认端点保留 `https://open.bigmodel.cn/api/coding/paas/v4`，优先使用环境变量 `LLM_BASE_URL`。按所有者选择保留 Coding Plan 配置，不自动切换按量端点。接口返回不代表必然抵扣套餐，额度适用范围和实际扣减以[智谱官方说明](https://docs.bigmodel.cn/cn/coding-plan/faq)及账户记录为准。

## Skill 与本地校验

[competition-scout Skill](.agents/skills/competition-scout/SKILL.md) 可由支持 Agent Skills 的编码助手执行。交互式助手用 `fetch_page.py` 保存证据，写提案后执行相同的校验和构建脚本，不必调用仓库的 GLM 执行器。Skill 依赖本仓库的数据合同和脚本。

无需密钥即可运行：

```bash
python3 -m unittest discover -s tests -v
python3 build_page.py
python3 ci_check.py
```
