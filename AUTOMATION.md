# 核验与更新任务模板

本文件可交给支持浏览网页及本地文件操作的维护智能体，也可作为人工维护清单。请在自己的调度器中配置项目目录、运行时间和 Python 环境；虚拟环境激活后统一使用 `python`，无需修改仓库写入本机路径。定时器不属于页面构建脚本。

## 前置条件

- 工作目录是本仓库根目录，`git remote -v` 指向你要维护的仓库；运行分支与 Pages 设置一致。
- 页面构建、API 列表、测试和 CI 使用标准库；若抓 SPA 列表，先按 README 安装 Playwright 和 Chromium。
- 整轮使用互斥锁，例如被忽略的 `.scout/daily.lock/owner.json`；记录运行 ID，清理时只释放自己持有的锁。若已有任务在运行则退出，避免并发改写。
- 保留其他人的未提交工作，不覆盖、不顺手提交。同步失败则停止；正常 `git pull --rebase origin main` 后记录基线 HEAD、原 ID 集合和 `archive.backup.json` 的 SHA-256。

## 抓取失败时的兜底顺序

按序尝试，成功即止，并在 `refresh-status.json` 的 `sourceResults[].fetchState` 记下实际通道。

1. `python scrape_spa.py`（Playwright）。
2. 浏览器直读：用 WorkBuddy 浏览器扩展控制本机 Chrome（已装扩展且已登录目标站点），打开列表页后逐屏读取可见 DOM 里的卡片 `href` 与倒计时。滚动时把指针停在页面右侧空白区，压在轮播卡片上会超时；页面内 `PageDown` 无效，用滚动工具。读到即记 `fetchState: browser`。
3. WebFetch 直接抓列表页正文。
4. 三级都失败才写进 `failedSources`，并注明失败到第几级。

Kaggle 的 `https://www.kaggle.com/api/v1/competitions/list` 即使在登录浏览器里也返回 `401 Unauthenticated`（要 API Key），不能当兜底。

## 可复制任务正文

你负责更新本目录的竞赛清单，直接阅读官方网页、规则和赛程并记录事实。不得调用外部 LLM API 或历史 AI/API 更新程序。以下抓取产物和运行状态只保存在被忽略的本地目录。

1. **续跑与排队**：读取 `events.json`、`sources.json`，以及存在时的 `.scout/source-progress.json`。优先处理未来 14 天内的强制节点、刚过期条目、冲突、新增与 `unclear/upcoming` 条目，再按最久未核验、优先级和方向轮转，目标每轮成功核验 5–15 条。不要因新快照覆盖而丢掉待处理候选。
2. **逐条核验**：打开官方详情、规则、赛程、报名入口及最新延期公告。有效正文才计成功，导航、登录和验证页不计。按字段保留短原文、实际 URL 和读取时间，更新报名、最终提交、资格、奖金与条件；强制报名、论文、提案、容器、DUA 和答辩分别记录。只有官方明确时刻和时区才写 `instant`，`day` 与其北京时间日期一致。
3. **资格与状态**：仅排除学生专属赛事，已有 ID 保留并附排除证据。资格未知保留 `unclear`。`open` 必须有仍可加入的证据，强制报名过期但提交仍开放为 `submission`；最终阶段未知不可直接关闭。风险才写 `warning`，失败不刷新原核验时间。
4. **发现与覆盖**：先固定本轮计划来源，再按 `sources.json` 的频率及上次进度抓取。运行 `python scrape_spa.py`、`python fetch_source_lists.py`，按需要调用其他 `--sources`。Grand Challenge API 跟随 `next` 到空，核对数量；NeurIPS 年度 Competition Track 公告逐条跟进官网。列表完成不等于候选资格和赛程已核验；保存未读分页、会议分支、候选 ID、年度/赛道、失败尝试及官方替代入口。
5. **去重与写回**：按官方详情 URL、平台 ID、年度和赛道去重，GC 子域标识站点。新条目使用稳定 ASCII slug，填齐现有 schema；核不到日期仍收录 `unclear` 并写具体原因。仅成功核验的条目更新 `verifiedAt` / `verifiedBy=agent`，并保持 `verification` 中的运行 ID、时间和证据一致。
6. **确定性收尾**：运行 `python daily_refresh.py`。随后写 `refresh-status.json`：`state`、北京时间秒级 `finishedAt`、去重成功的 `verifiedIds` / `verified`、计划源 `sourceResults` / `sourcesTotal` / `sourcesOk`、`failedSources`、待核 ID、覆盖说明和唯一 `runId`。`runner` 使用 CI 已支持的 `codex-agent` 或 `workbuddy-agent`，如实记录实际运行者。`ok` 仅用于全部目标完成，部分完成为 `partial`；不要通过修改时间伪装重新核验。
7. **验收与发布**：确保未设置用于历史复现的 `BUILD_NOW` / `BUILD_TODAY`。依次运行 `python build_page.py`、`python ci_check.py`、`python check_release.py`，必须全部通过；最后一次更改后再次验收。保留全部原 ID，备份哈希不变，公开目录仅有 `index.html` 与 `.nojekyll`。
8. **Git 与部署**：审查差异，仅显式暂存本轮应发布文件，例如 `events.json`、`sources.json`、`refresh-status.json`、`docs/index.html`；提醒日志与抓取结果留在本地。无暂存差异不提交，有变更正常 commit/push，禁止 force push。若远端有新提交，安全同步、重建及验收后再推送。推送后检查 HTTP 200、精确 `finishedAt` 对应显示和线上/本地 HTML SHA-256；若有部署延迟，等 60 秒重试一次，仍未匹配则报告部署待确认。

**边界**：不删除赛事 ID、不改备份、不更改仓库可见性、不创建自定义 GitHub Actions、不提交凭据或个人记忆。`partial` 仅在已改动事实证据充分、页面明确展示缺口且 CI 通过时可发布；关键失败必须保留成果并报告。

## 低打扰结果

没有新增、状态翻转、重要资格/费用/提交要求变化或七天内到期变化，且全过程正常时，只保存本轮无变更结果；重要变化、源或目标未完成、同步/验收/推送失败、部署待确认或需要人工处理时通知。报告实际核验条数、新增数、失败与积压、推送及上线结果，不把列表数量当作成功核验数量。
