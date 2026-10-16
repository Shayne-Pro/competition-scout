# 贡献说明

欢迎更正赛事事实、改善通用抓取和校验逻辑，或完善文档。独立搭建自己的清单请先看 [CUSTOMIZATION.md](CUSTOMIZATION.md)；数据维护流程见 [AUTOMATION.md](AUTOMATION.md)。

## 报告和修正赛事信息

提交赛事名称、官方详情 URL、具体年度/赛道/阶段、短原文及读取时间。说明原记录哪里有误、官网明确了什么。非官方转述可作为发现线索，不能替代日期或资格证据。日期不明、资格未知时保留 `unclear`；不要删除旧 ID，也不要把论文或提案截止当作参赛截止。

## 修改代码

1. 从最新版本创建自己的分支，一次改动解决一个问题。
2. 在独立目录中测试；不要借测试刷新生产数据的核验时间、删除原始条目或改备份。
3. 运行 `python -m unittest -q test_refresh test_source_lists test_release` 和 `python check_release.py`。数据或页面逻辑改动还需重建页面并运行 `python ci_check.py`；历史快照按 README 中的固定时间方式复现。
4. PR 写明问题、修改后的行为、验证结果；页面外观改变时附截图。纯文档修改检查命令、链接与描述即可。

不提交凭据、Cookie、个人记忆、登录后的参赛仪表盘、原始抓取快照或本机绝对路径。提醒和运行日志保存在本地。发现可能含凭据的内容时，不要在 Issue 中粘贴秘密值。

代码贡献沿用 [MIT License](LICENSE)。第三方内容、数据和素材仍须遵守其原授权，参见 [NOTICE.md](NOTICE.md)。
