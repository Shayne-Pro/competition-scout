# Competition Scout

CV、医学影像、3D、大模型与 Agent 等方向的竞赛清单。保存官方来源、报名与提交节点、参赛限制和核验记录，生成可筛选的静态页面。

[查看竞赛清单](https://shayne-pro.github.io/competition-scout/)

[快速开始](#快速开始) · [搭建自己的清单](CUSTOMIZATION.md) · [更新任务模板](AUTOMATION.md) · [参与贡献](CONTRIBUTING.md) · [MIT 许可](LICENSE)

项目由 **Python 标准库脚本 + 官方事实核验 + 静态页面** 组成。脚本处理日期、分页、构建和校验；维护者或智能体负责阅读官方规则并判断事实。运行构建脚本不会自动完成赛事核验，也不会调用外部 LLM API。

线上页面是正在维护的清单实例；仓库同时提供可复用脚本、事实规则和 [虚构示例](examples/)。当前竞赛数据与来源随版本保存，本机凭据、抓取快照、运行记忆和调度器配置单独保留在维护者环境中。想换成自己的研究方向或平台来源，见 [定制指南](CUSTOMIZATION.md)。

## 快速开始

需要 Python 3.10 或以上版本，已在 Python 3.13 下验证。以下命令适用于 macOS / Linux 的 POSIX shell；其他系统可使用等效的虚拟环境激活命令。

```bash
git clone https://github.com/Shayne-Pro/competition-scout.git
cd competition-scout
python3 -m venv .venv
. .venv/bin/activate

# 构建和浏览已有数据，无须安装第三方包。
python build_page.py
python -m http.server 8000 --directory docs
```

打开 <http://localhost:8000>。仓库处于私有状态时，克隆需要有访问权限；使用源码压缩包时，可从解压后的项目目录开始操作。

### 测试和复现

```bash
python -m unittest -q test_refresh test_source_lists test_release
python check_release.py
```

发布检查 `python ci_check.py` 要求核验摘要的日期与构建日期一致。若只是复现仓库保存的历史快照，应使用其真实核验时间，而非把 `finishedAt` 改成今天：

```bash
export BUILD_NOW="$(python -c 'import json; print(json.load(open("refresh-status.json", encoding="utf-8"))["finishedAt"])')"
export BUILD_TODAY="${BUILD_NOW%%T*}"
python build_page.py
python ci_check.py
unset BUILD_NOW BUILD_TODAY
```

复现成功只说明该快照通过校验，不表示官网今天仍保持相同规则。

## 可选：抓取官方列表

浏览器抓取需要 Playwright 和 Chromium；标准库 API 脚本无须安装它们。

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium

# 默认抓取 Kaggle、天池和讯飞，默认产物在被忽略的 .scout/ 下。
python scrape_spa.py

# 其他动态列表，可显式指定输出位置和来源。
python scrape_spa.py --output .scout/secondary_snapshot.json --sources devpost ascend baidu tencent zindi

# Codabench 全量列表及 EvalAI 当前、未来、历史列表。
python fetch_source_lists.py
```

两个抓取脚本均以退出码 `0` 表示其定义的抓取目标成功，`2` 表示存在失败或不完整范围。应读取产物中的源级状态和覆盖说明，不以退出码代替赛事规则核验。

Kaggle API 凭据是可选的：脚本支持 `KAGGLE_USERNAME` / `KAGGLE_KEY`，或当前用户目录下的 `.kaggle/kaggle.json`。不要把凭据放入仓库。没有凭据时会尝试公开网页；若只取得导航、登录或验证页面，记录失败，交由维护者使用正常浏览器核验。不要绕过验证码或关闭证书校验。

列表完整与规则已核验是不同状态：`fetchState` 表示是否取得有效内容，列表的 `inventoryState` / `coverageState` 描述已读范围，本轮 `sourceResults.state` 表示计划范围与候选处理进度。API 的 `complete` 只表示分页和数量校验完成。

## 更新与发布

完整流程和可复制的智能体任务模板见 [AUTOMATION.md](AUTOMATION.md)。定时运行需由自己的调度器配置项目工作目录；仓库不绑定特定电脑路径，不包含可自动核验全部赛事的托管服务。

1. 同步仓库并保存本轮 ID 集合与备份哈希。
2. 阅读官方详情、规则、赛程及延期公告，更新数据与逐条证据；抓取列表只用于发现候选。
3. 运行 `python daily_refresh.py`，按已知截止推导状态与本地提醒。
4. 写入真实的 `refresh-status.json`，再运行 `python build_page.py` 和 `python ci_check.py`。
5. 审查差异，通过 `python check_release.py` 后，显式暂存需要发布的文件并正常提交推送。

GitHub Pages 发布源为 `main` 分支的 `/docs`。`docs/` 仅允许 `index.html` 和 `.nojekyll`；不要放入源码、抓取快照或凭据。推送后应检查线上 HTTP 状态、精确核验时间及 HTML 哈希。仓库可见性与 Pages 的可用性取决于账户套餐和设置，见 [GitHub Pages 官方说明](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)。

## 数据与目录

| 文件或目录 | 用途 | 是否进入版本库 |
| --- | --- | --- |
| `events.json` | 赛事、阶段、资格、证据和逐条核验时间 | 是 |
| `sources.json` | 官方检索源、扫描频率和来源覆盖 | 是 |
| `refresh-status.json` | 最近一轮完成时间、成功条目和未完成范围 | 是 |
| `archive.json` / `archive.backup.json` | 历史数据及保留备份 | 是；备份不随更新改写 |
| `docs/` | 生成的公开页面 | 是 |
| `.scout/` | 抓取结果、候选队列、锁、基线及临时证据 | 否 |
| `notified.json` / `runs-log.jsonl` | 本地提醒去重及运行日志，缺失时由刷新脚本创建 | 否 |
| `.workbuddy/` / `.codex/` / `.env*` | 本地智能体状态或凭据 | 否；可提交无秘密的 `.env.example` |

### 事实与日期规则

- 只记录官网能印证的事实。日期或资格无法确认时保留 `unclear`，在 `warning` 中写具体缺口；失败核验保留旧事实和旧核验时间。
- 唯一赛事排除条件是“仅限在校学生”。历史条目保留 ID，以 `exclusion.reason=student-only` 和官方证据记录，页面隐藏；混合资格和资格未知的赛事保留。
- `entry` 与 `submit` 分别表达报名和参赛提交节点；开始节点标 `kind=start`，可选报名标 `mandatory=false`。论文、提案、报告和答辩不可冒充最终参赛截止。
- `day` 是北京时间日期。仅在官方明确时刻和时区时填写带 offset 的 `instant`；`text` 保留原时区及北京换算。只有日期或时区未知时不猜时刻。
- `verifiedAt` 表示该条实际核验完成时间；成功时间采用带 `+08:00` 的 ISO 格式，精确到秒。页面本轮时间来自 `refresh-status.json.finishedAt`，不表示全部记录当天均已核验。
- Grand Challenge 的状态和结束日期只作候选信号，须读赛事子站确认。详情 URL、平台赛事 ID、年度和赛道共同参与去重，不能仅按标题或平台首页合并。

| 赛事状态 | 含义 |
| --- | --- |
| `open` | 有仍可新加入的证据 |
| `submission` | 强制报名已结束，已报名者仍可提交 |
| `upcoming` | 尚未开始 |
| `unclear` | 日期、资格或阶段等关键事实待确认 |
| `closed` | 已确认参赛提交阶段均结束 |
| `practice` | 长期评测或练习 |

本轮 `ok` / `partial` / `failed` 与赛事状态独立。部分结果可以展示，但必须公开缺口；总条目数不能当成本轮成功核验数。

## 贡献

欢迎提交官方来源支持的日期、资格或提交要求更正。请提供赛事名称、具体阶段、官方 URL、短原文和读取时间；对已有条目保持 ID 稳定。修改逻辑时运行测试，修改数据时重建页面并通过发布检查。抓取快照、个人记忆、登录信息和参赛仪表盘内容不进入提交。贡献步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)，[赛事更正表单](https://github.com/Shayne-Pro/competition-scout/issues/new?template=competition.yml) 随仓库访问权限开放。

## 许可证与未来公开

本项目原创代码及文档采用 [MIT License](LICENSE)，第三方内容的权利边界见 [NOTICE.md](NOTICE.md)。

仓库可见性属于维护者的决定，构建脚本与发布流程不做变更。

2026-11-19 对全部 35 次提交、147 个历史 blob 做过一次公开前审查：当前版本无凭据、无本机绝对路径、无个人信息；历史提交中出现过的唯一凭据是早期 `build_page.py` / `index.html` 内嵌的 WorkBuddy 云端 publishableKey（已于 547be53 移除，仅存于历史），其余为环境变量名。`.gitignore` 不会清除历史，若该凭据对应的云项目仍在用，应先停用或轮换再公开。

若需要交付不包含 Git 历史的源码包，可在提交并验收后导出：

```bash
mkdir -p .scout
git archive --format=zip --output=.scout/competition-scout-source.zip HEAD
```

源码包不携带旧提交记录；公开前仍应检查实际压缩包内容。
