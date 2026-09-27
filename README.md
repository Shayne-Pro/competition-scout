# Competition Scout

通过仓库内的 Agent Skill 发现与核验 AI 竞赛，每日由 GitHub Actions 更新静态页面。

执行层是轻量 Python 工具调用循环，沿用已有 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 三个 Secrets。没有 OpenCode、Node 或额外 Agent 框架依赖。Python 标准库负责模型请求、网页读取和数据校验；Playwright 只用于 JavaScript 网页的浏览器回退。

## 工作方式

1. `scout.py prepare` 读取 `sources.json`，准备到期来源和最多 20 条待复核赛事。待确认、待发布、近期/历史关闭记录都能进入队列；按上次尝试时间轮转，避免失败条目长期占用额度。
2. `agent_refresh.py` 加载 [competition-scout Skill](.agents/skills/competition-scout/SKILL.md) 和输出合同，调用 GLM。模型可以读取任务、抓网页及详情链接、记录来源、记录赛事或失败原因、完成提案。
3. 模型没有 shell、任意文件读写或 Git 工具。逐条提案存入 `.scout/`；证据摘录必须能在本轮实际抓到的网页中找到。抓取源只接受公开 HTTP(S) 地址。
4. `scout.py apply` 校验本轮 ID、原始数据指纹、完整来源/目标记账、赛事身份、日期、资格、引用和状态，再合并。未知日期会清空旧值；学生专属条目保留为 excluded，公开页面不展示。
5. `daily_refresh.py` 根据已核实的截止时刻计算状态，`build_page.py` 构建页面，`ci_check.py` 检查数据与页面。页面区分构建时间、最近成功核验和本轮失败/部分完成。
6. 独立 publish job 只复制六个规定的发布文件。若扫描期间 main 有新提交，会停止发布，避免覆盖并发修改；成功后提交到 main 并请求现有 GitHub Pages 分支构建。

## 每日执行与试运行

工作流是 `.github/workflows/daily-refresh.yml`，每天 UTC 00:20（北京时间 08:20）计划执行。GitHub 的定时触发可能延迟。

手动触发默认 `dry_run=true`：运行真实模型与抓取，上传结果和证据，**不修改 main、不部署页面**。分支运行始终禁止发布，即使 dry_run=false。主分支手动发布需要明确设 dry_run=false。每轮最多 100 次模型请求轮次、180 次工具调用、65 次网页抓取、20 分钟 Agent 运行预算；单模型请求最多重试一次。重试也消耗额度。可用 max_steps、target_limit 做较小的调试运行。

模型或抓取失败时保留既有事件数据，页面可发布本轮失败状态，Actions 同时显示失败。部分来源失败会显示 partial，未完成项目明确记为 deferred；不会把本轮构建日当作全表核验日。

在本仓库启用前先合并改造分支。已有 Secrets 和 `main /` 的 Pages 设置继续使用；无需新建密钥。源配置和扫描结果分别在 `sources.json`、`source-state.json` 中，运行摘要写入 `refresh-status.json`，历史逐轮追加到 `runs-log.jsonl`。

**API 计费边界：** 当前默认端点保留原仓库的 `https://open.bigmodel.cn/api/coding/paas/v4`，并始终优先使用 Secret `LLM_BASE_URL`。智谱官方说明自建应用不属于 Coding Plan 的通用额度适用范围；接口能返回不代表必然抵扣套餐。本仓库按所有者选择保留现有配置，不伪装为其他客户端，也不自动切换到按量端点。账户额度与实际抵扣应以智谱记录为准。参见 [官方 FAQ](https://docs.bigmodel.cn/cn/coding-plan/faq)。

## 本地使用

Python 3.9+（Actions 固定为 3.12）：

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

旧入口 `python3 ai_update.py` 是 prepare → Agent → apply 的兼容包装。旧 `scrape_spa.py` 不再被每日工作流调用；动态页面由 Agent 根据需要请求 render=true。提醒目前仅记录候选，不声称已发送消息。

验证无需密钥和联网：

```bash
python3 -m unittest discover -s tests -v
python3 build_page.py
python3 ci_check.py
```

历史数据保持原有文案与条目 ID，不会被一次性伪装成“Agent 已核验”。没有新日期类型/时区元数据的旧记录标为待复核，暂不用于自动倒计时或日期状态翻转，随后由每日队列逐步补齐。来源被阻断时，复核完成时间无法保证。

## Skill 的复用边界

`.agents/skills/competition-scout/` 使用标准 SKILL.md 格式，可以被支持 Agent Skills 的编码助手发现。仓库的数据 schema、`sources.json` 和确定性脚本也是工作流的一部分；这不是脱离仓库即可自动发布任意网站的通用插件。

交互式编码助手也可直接执行 Skill：用 `fetch_page.py` 抓取并保存证据，写提案后调用相同的校验与构建脚本，无需调用仓库的 GLM 执行器。详细命令见 Skill。

工具调用协议参考 [智谱 Function Calling](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)。新增字段或更换模型时，先执行离线回归，再在非 main 分支做有预算限制的 dry run，查看提案、证据与页面产物。
