# Competition Scout

CV / 大模型 / 搜广推 竞赛清单：逐条核对官方来源后确认还能参加的具体赛题。

公开页面：https://shayne-pro.github.io/competition-scout/

## 架构

- **页面**：纯静态，由 `build_page.py` 从 `events.json` 生成到 `docs/index.html`；GitHub Pages 部署源为 `main /docs`（仓库为私有，公开 Pages 需 GitHub Pro 或更高套餐）。
- **更新**：由 Codex 定时任务（每天北京时间 08:30）驱动，原 WorkBuddy 任务暂停。Codex 直接读取官网核验、发现赛事并写回数据，**不调用外部 LLM API**。本机须开机并保持 Codex 运行。
- **本地确定性收尾**：`daily_refresh.py` → 写本轮 `refresh-status.json` → `build_page.py` → `ci_check.py` → 正常提交推送。公开官网/API 与 GitHub 发布可用，不使用额外云算力、数据库或模型服务；不创建自定义 Actions，保留 Pages 内置部署。

## 脚本

```bash
# 日期翻转与 7 天提醒（纯日期运算，无网络）
python3 daily_refresh.py
# 重建页面（输出 docs/index.html；核验时刻取 refresh-status.json 的 finishedAt）
python3 build_page.py
# 最终自检（数据日期、状态、证据/来源覆盖、页面核验时间及公开目录）
python3 ci_check.py
# 截止、CI 和抓取失败回归测试
python3 -m unittest -q test_refresh
# 抓 Kaggle/天池/讯飞三个 SPA 列表页（Playwright，可选，供人工/智能体浏览）
python3 scrape_spa.py
```

数据文件：`events.json`（赛事条目）、`sources.json`（检索源注册表）、`notified.json`（提醒去重）、`runs-log.jsonl`（每日运行日志，同日去重）、`refresh-status.json`（最近一轮核验状态，页面横幅与其 `finishedAt` 即「核验日期」）。

## 数据规则

- 只用官网能印证的内容；日期拿不准标 `status=unclear` 并在 `warning` 写明卡在哪，禁止推测补全。
- 唯一排除规则：仅限在校学生参加的赛事不收录。
- grand-challenge 的 `status` 与 `end_date` 不作为官网赛程证据。组合日期条件只用于优先核验，缺字段的候选保留并读子站；按 API `next` 全量分页，报告实际覆盖与失败。
- `day` 是北京时间日期；`instant` 有官方明确时刻时区才写带 offset 的 ISO。日期和精确时刻必须一致，截止日期不得充当开始日期。
- `verifiedBy` 记录核验来源；自动状态推导另存 `statusDerivation`，不覆盖已有核验者或核验时间。本轮 runner 为 `codex-agent`。
- `ok/partial/failed` 分别表示本轮全部完成、部分完成、关键失败。页面公开本轮核验条数、发现源覆盖与未完成来源；全表记录数不是今日全部已核验。
- 发布只暂存明确允许的文件；不提交 `.scout`、快照、凭据或智能体记忆。`SCOUT_BASELINE` 可指向本轮 ID/备份哈希基线，让 CI 检查条目和备份保存。
