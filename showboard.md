# 热讯工坊 Showboard

## 一、问题（假设）

### 1.1 项目背景问题

短视频内容生产通常需要同时完成热点发现、事实核查、选题判断、脚本撰写、视频剪辑和运营发布。个人创作者在实际执行中容易遇到以下问题：

- 热点信息来源分散，选题收集和筛选效率低。
- 新闻转载链路复杂，真实性、时效性和重要性难以稳定核验。
- 爆款内容的传播结构依赖个人经验，难以标准化复用。
- 脚本、剪辑和运营环节衔接不紧密，重复劳动较多。
- 从选题到发布缺少统一的任务状态、岗位边界和产物归档。

### 1.2 核心假设

- 假设 A：将内容生产拆分为热点监控、爆款分析、文案、剪辑和运营等明确岗位，可以降低单人创作的认知负担。
- 假设 B：Agent 分工结合工作流编排，比单一聊天窗口更适合持续产出结构化的短视频方案。
- 假设 C：在没有在线模型 Key 时使用本地模板回退，可以支持前期演示和流程体验，降低项目接入门槛。
- 假设 D：为不同岗位设置独立工作区，并按任务保存 Markdown 和 JSON 产物，可以提升过程可追溯性和复盘效率。
- 假设 E：在热点进入后续生产前加入来源、发布时间和独立域名检查，可以减少未经核验的信息被继续加工和发布的风险。

### 1.3 项目目标

1. 构建“热点线索 → 事实核验 → 爆款分析 → 脚本 → 剪辑方案 → 运营方案”的内容生产原型。
2. 支持老板输入领域、方向、受众和目标时长，执行完整工作流或单独调用某个环节。
3. 在本地提供可视化调度、任务恢复、项目导入导出和服务状态控制。

## 二、实践方法与过程

### 2.1 技术方案

- 后端使用 Python 3.11+、FastAPI、Pydantic 和 OpenAI 兼容客户端。
- 前端使用 React、TypeScript、Vite 和 Lucide 图标。
- Python 依赖由 `uv` 管理，声明在 `pyproject.toml`，版本锁定在 `uv.lock`。
- 项目通过 Windows PowerShell 脚本启动，前端默认使用 5173 端口，后端默认使用 8017 端口。
- 工作流运行状态、岗位产物和员工独立工作台的最新结果以本地文件保存，主要写入 `workspaces/runs/<run_id>/`；项目导入导出覆盖以上全部项目产物。

### 2.2 完整工作流过程

1. 老板提交 `TopicSeed`，包括领域、方向、受众和目标时长。
2. 热点监控员调用 `news-aggregator-skill` 获取公开来源，整理 3–5 个候选热点。
3. 系统检查候选的来源 URL、发布时间、来源主张和交叉核验信息。
4. 只有标记为 `verified` 且至少来自两个不同域名来源的候选，才进入爆款分析；不满足条件时，工作流停止并保留失败检查点。
5. 爆款分析师输出传播钩子、冲突点、内容结构和风险提示。
6. 文案助手根据选题和分析结果生成带时间段的短视频口播脚本。
7. 视频剪辑员生成画幅、素材、字幕、配音和 MoneyPrinterTurbo 导出方案。
8. 运营大师生成标题、封面文案、发布时间、评论引导和复盘指标。
9. 系统将各岗位产物写入独立目录，并在 `boss/run-summary.json` 中保存运行摘要。

### 2.3 运行设计

- 没有 `AI_API_KEY` 时使用本地模板回退，实时热点和在线模型能力可通过配置在线服务启用。
- 热点抓取和模型调用分别支持超时设置，`0` 表示不限时；视频剪辑员的 MoneyPrinterTurbo 渲染阶段始终不限时。设置可在前端保存到 `workspaces/runtime-settings.json`。
- 任务状态包括 `queued`、`running`、`completed` 和 `failed`。
- 任务会记录当前阶段和错误信息，并支持通过恢复接口从检查点继续。
- 服务启动时会加载已保存的运行状态，方便展演过程中保存和恢复项目。

### 2.4 岗位与 Skill 接入

核心流水线由热点监控员、爆款分析师、文案助手、视频剪辑员和运营大师组成。扩展岗位包括产品经理、程序员、股票助手和心理疗愈师。

当前接入的专项 Skill 包括：

- 热点监控：`workspaces/agents/hotspot_monitor/skills/news-aggregator-skill/`
- 股票助手：`workspaces/agents/stock_assistant/skills/stock-analysis/`
- 视频剪辑：`workspaces/agents/video_editor/skills/moneyprinterturbo-video/`
- 运营：`workspaces/agents/operator/skills/newmedia-operations/`
- 产品经理：`workspaces/agents/product_manager/skills/Product-Manager-Skills/`
- 心理疗愈：`workspaces/agents/healer/skills/mental-health-assistant/`

## 三、作品功能介绍

### 3.1 调度台功能

| 功能面板 | 作品功能 |
| --- | --- |
| 控制台 | 启动完整工作流，查看流水线阶段、热点候选和岗位产物。 |
| 热点雷达 | 输入领域和方向，单独扫描公开热点线索。 |
| 股票分析 | 针对股票、财经和股票新闻生成分析报告，并展示免责声明。 |
| 脚本工坊 | 单独生成 30–240 秒范围内的中文短视频口播脚本。 |
| 剪辑队列 | 查看剪辑方案，并尝试调用 MoneyPrinterTurbo 生成真实成片。 |
| 互动回复 | 展示评论分类、优先级和 Agent 分配的互动处理界面。 |
| 员工 | 查看岗位职责、工作状态、Skill 和独立工作区。 |
| 设置 | 查看 AI 配置、调整超时、导入导出项目和控制本地服务。 |

### 3.2 核心接口

- `GET /api/health`：服务健康检查。
- `GET /api/status`：查看 AI Key、Base URL、模型和当前运行模式。
- `GET /api/agents`：获取 Agent 岗位信息。
- `POST /api/topics/scout`：扫描热点候选。
- `POST /api/scripts/generate`：单独生成脚本。
- `POST /api/stocks/analyze`：执行股票分析。
- `POST /api/workflows/hot-video`：执行完整热视频工作流。
- `GET /api/workflows`、`GET /api/workflows/{run_id}`：查询任务及状态。
- `POST /api/workflows/{run_id}/resume`：恢复失败任务。
- `/api/workflows/{run_id}/export` 和 `/api/workflows/import`：导出、导入项目。
- `/api/video/moneyprinterturbo/status` 和 `/api/video/moneyprinterturbo/run`：检查并调用剪辑工具。

### 3.3 产物与工作区

每次完整任务会按岗位保存产物：

```text
workspaces/runs/<run_id>/
├── hotspot_monitor/hotspot_monitor.md
├── viral_analyst/viral_analyst.md
├── copywriter/copywriter.md
├── video_editor/video_editor.md
├── operator/operator.md
├── boss/run-summary.json
└── run-state.json
```

其中 `run-state.json` 用于保存任务状态和恢复信息，`run-summary.json` 用于汇总本次任务的输入、热点和各岗位输出。

### 3.4 参展呈现方式

参展时以“老板发出指令”为起点，现场展示一条内容从热点到发布的完整路径：

1. 在控制台输入领域、方向、受众和时长。
2. 在热点雷达中展示来源汇聚、候选选题和核验信息。
3. 进入脚本工坊，展示 AI 员工如何将选题转化为口播脚本。
4. 在剪辑队列查看画幅、素材、字幕、配音和成片方案。
5. 在运营模块展示标题、封面文案、发布时间和互动策略。
6. 回到员工与设置页面，展示岗位分工、独立工作区和本地调度能力。

作品希望呈现的核心观念是：AI 不只是一个聊天窗口，而是一支拥有岗位、技能、工作区和协作流程的内容生产团队。
