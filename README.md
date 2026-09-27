# Competition Scout

CV / 大模型 / 搜广推 竞赛清单：逐条核对官方来源后确认还能参加的具体赛题。

公开页面：https://shayne-pro.github.io/competition-scout/

## 架构

- **页面**：纯静态，由 `build_page.py` 从 `events.json` 生成到 `docs/index.html`；GitHub Pages 部署源为 `main /docs`（仓库为私有，公开 Pages 需 GitHub Pro 或更高套餐）。
- **更新**：由 WorkBuddy 定时任务（每天 08:30）驱动——WorkBuddy 智能体自己读官网核验、发现新赛事、写回数据，**不依赖任何外部 LLM API key**；确定性部分（日期翻转、构建、自检）由本仓库脚本完成。
- **无 Actions、无云服务、无 API 依赖**：`daily_refresh.py`（日期翻转+提醒去重）→ `build_page.py`（构建）→ `ci_check.py`（自检）均可独立运行。

## 脚本

```bash
# 日期翻转与 7 天提醒（纯日期运算，无网络）
python3 daily_refresh.py
# 重建页面（输出 docs/index.html；核验时刻取 refresh-status.json 的 finishedAt）
python3 build_page.py
# 自检（行数 / id 唯一 / 结构完整）
python3 ci_check.py
# 抓 Kaggle/天池/讯飞三个 SPA 列表页（Playwright，可选，供人工/智能体浏览）
python3 scrape_spa.py
```

数据文件：`events.json`（赛事条目）、`sources.json`（检索源注册表）、`notified.json`（提醒去重）、`runs-log.jsonl`（每日运行日志，同日去重）、`refresh-status.json`（最近一轮核验状态，页面横幅与其 `finishedAt` 即「核验日期」）。

## 数据规则

- 只用官网能印证的内容；日期拿不准标 `status=unclear` 并在 `warning` 写明卡在哪，禁止推测补全。
- 唯一排除规则：仅限在校学生参加的赛事不收录。
- grand-challenge 的 `status` 与 `end_date` 字段不可信（老赛标 OPEN、假 end 常见），必须用 `start(≥2025-01-01) + end(今天≤end≤2027-12-31) + modified(≥2025-09-01)` 组合过滤。
- 每条的 `verifiedBy` 记录核验者：`human`（人工）/ `ai`（外部 API，历史遗留）/ `agent`（WorkBuddy 智能体）/ `auto`（系统按日期推算）。
