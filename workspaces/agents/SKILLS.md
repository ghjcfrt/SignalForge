# 员工 Skill 安装登记

本文件记录热讯工坊各 AI 员工的专属 skill 来源。第三方项目保留原始 README / LICENSE；这里仅做项目级登记和归属说明。

| 员工 | 岗位 | Skill | 安装路径 | 来源 | 许可证 / 状态 |
|---|---|---|---|---|---|
| 赵爽 | 热点监控员 | `bilibili-search` | `workspaces/agents/hotspot_monitor/skills/bilibili-search/` | ClawHub/Volces，owner `excalibursssooo`，version `0.1.0` | MIT-0，已安装 |
| 小李 | 视频剪辑员 | `moneyprinterturbo-video` | `workspaces/agents/video_editor/skills/moneyprinterturbo-video/` | `https://github.com/harry0703/MoneyPrinterTurbo/tree/main/docs/skill` | MIT，默认剪辑链路 |
| 星辰 | 爆款分析师 | `space-xhs-hotspot` | `workspaces/agents/viral_analyst/skills/creator-buddy/xhs-Skills/space-xhs-hotspot/` | `https://github.com/SpaceZephyr/creator-buddy` | MIT，公开热点分析；至少两个独立来源交叉验证后才能发布 |
| 尤道理 | 运营大师 | `newmedia-operations` | `workspaces/agents/operator/skills/newmedia-operations/` | ClawHub/Volces，owner `swcxy12315`，version `1.0.0` | 上游未声明许可证，已安装 |
| 方舟 | 产品经理 | `Product-Manager-Skills` | `workspaces/agents/product_manager/skills/Product-Manager-Skills/` | `https://github.com/deanpeters/Product-Manager-Skills` | CC BY-NC-SA 4.0，已安装 |
| 周周 | 心理疗愈师 | `mental-health-assistant` | `workspaces/agents/healer/skills/mental-health-assistant/` | ClawHub/Volces，owner `ttoooong`，version `2.1.0` | 上游未声明许可证，已安装 |
| 林量 | 股票助手 | `stock-analysis` | `workspaces/agents/stock_assistant/skills/stock-analysis/` | `https://github.com/liusai0820/Stock-Analysis-Skill` | MIT，已安装；财经/股票新闻默认调用 |

## 当前未单独安装 Skill 的岗位

以下岗位目前使用项目内置提示词和工作流逻辑：

| 员工 | 岗位 | 当前能力来源 |
|---|---|---|
| 洛一 | 文案助手 | `backend/app/workflows.py` 的 90-120 秒脚本提示词 |
| 阿栈 | 程序员 | 项目内置开发/自动化岗位提示词 |

后续如果要给这些岗位安装更专门的 skill，可以继续放在各自的 `workspaces/agents/<agent_id>/skills/` 下，并在这里登记来源。
