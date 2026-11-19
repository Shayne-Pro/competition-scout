# 搭建自己的竞赛清单

线上清单展示当前维护的赛事；仓库提供可复用的构建、日期处理、抓取和验证代码。实际资格与规则仍需维护者或智能体读官方页面确认。

## 用虚构示例试跑

`examples/` 的赛事和官方链接均为虚构示例，核验数为零，不会访问真实官网。以下命令仅把页面写入本地临时目录，适合在安装 Python 后先了解效果：

```bash
mkdir -p .scout/demo/docs
cp examples/*.json .scout/demo/
touch .scout/demo/docs/.nojekyll
EVENTS_DIR=.scout/demo OUT_HTML=.scout/demo/docs/index.html BUILD_NOW=2026-01-01T00:00:00+08:00 BUILD_TODAY=2026-01-01 python build_page.py
EVENTS_DIR=.scout/demo BUILD_NOW=2026-01-01T00:00:00+08:00 BUILD_TODAY=2026-01-01 python ci_check.py
python -m http.server 8001 --directory .scout/demo/docs
```

打开 <http://localhost:8001>。示例时间只用于重现示例，不是最近核验时间，也不能用于生产发布。

## 配置位置

| 要改的内容 | 位置与约束 |
| --- | --- |
| 维护哪些赛事 | `events.json`；先按现有完整 schema 填写，未知事实留空并标 `unclear` |
| 从哪里发现赛事 | `sources.json`；保留官方 URL、扫描频率、失败与后续范围 |
| 方向标签与排序 | 条目的 `tags` / `priority`；新方向同步调整 `build_page.py` 的 `TAGSLUG` / `TAGORDER` |
| 论文通道标记 | 条目的 `paper`（一句话写清形式与门槛，留空表示没有）；驱动页面「有论文通道」筛选与行内徽标 |
| 站名、文案与样式 | `build_page.py`；如改页面标题，须同步 `ci_check.py` 中的标题检查 |
| 页面输入与输出 | `EVENTS_DIR`、`OUT_HTML`，可用于独立测试目录；CI 从 `EVENTS_DIR/docs` 读取页面 |
| 核验偏好和更新频率 | [AUTOMATION.md](AUTOMATION.md) 中的任务模板，以及你自己的调度器配置 |
| 本地凭据、锁、进度与日志 | 用户环境、`.scout/` 和被忽略的本地文件；不进入版本库 |

初始化自己的独立站时，可用示例作为起点，把虚构记录替换为有官方证据的实际赛事，调整 README 中的站点和仓库链接，再设置自己的 Pages 发布源。向本项目贡献时则保留现有赛事 ID 与备份。

现有真实条目及来源是清单实例的数据，公开站点可直接查看；它们不是安装后会自动重新核验的“内置知识”。使用真实条目时保留来源及核验时间。

## 开源组织方式参考

文档组织参考了 [AIHOT 的 README](https://github.com/KKKKhazix/AIHOT#readme) 中对线上实例、可复用代码、示例与定制入口的区分。本项目采用适合竞赛清单的实现，未复制其代码、提示词、界面或品牌素材。
