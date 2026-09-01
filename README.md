# 热讯工坊（SignalForge）

热讯工坊是一个本地运行的 AI 内容生产调度台，把“热点线索 → 事实核查 → 爆款分析 → 脚本 → 剪辑方案 → 运营发布”拆成多个岗位 Agent。项目适合用来验证一人公司式内容生产流程、Agent 分工和结构化产物沉淀。

当前项目是可运行原型，不承诺已经具备生产环境级别的新闻准确率、视频成片成功率或运营效果。

## 当前能力

- 总览：执行完整的热视频工作流，查看阶段状态、热点和岗位产物。
- 热点雷达：调用 `news-aggregator-skill` 抓取公开来源，并要求模型基于来源整理选题。
- 真实性门禁：至少两个不同域名的独立来源交叉验证后，热点才会进入后续生产阶段；否则任务停止并保留失败检查点。
- 爆款分析：针对已核验选题调用 SocialDataX 小红书笔记搜索，按高互动样本拆解标题、内容结构和传播钩子；该接口只用于爆款分析，不参与新闻抓取或事实核验。
- 脚本工坊：单独生成指定主题的短视频脚本，默认目标时长为 30–240 秒。
- 股票分析：调用 `stock-analysis` Skill 生成股票/财经分析，可选接入 Tushare、Tavily、SerpApi。
- 剪辑队列：生成 MoneyPrinterTurbo 剪辑方案，并可调用其 helper 尝试真实成片。
- 互动回复、员工、设置：展示岗位信息、评论处理样例、AI 状态、超时设置、项目导入导出和本地服务控制。
- 无 Key 回退：没有 `AI_API_KEY` 时仍可启动并验证本地模板、接口和前端流程；需要实时热点和在线模型时必须配置 Key。
- 任务持久化：运行状态会写入 `workspaces/runs/<run_id>/run-state.json`，服务重启后会尝试恢复已保存的任务。
- 阶段化执行：完整模式在后台逐阶段执行并实时保存；总览页也可以逐个岗位执行下一步，失败后从当前阶段继续。
- 执行日志：每个任务会生成 `run.log.jsonl`，界面同步展示阶段、错误类型和详细原因。
- 爆款分析可切换 SocialDataX 或手写策略；SocialDataX 模式会先取高互动排行，再按已核验选题搜索样本，视频样本会尝试提取口播。
- 热点候选会先完成全量排序和来源核验，再选择进入后续生产的候选；运行中可以手动停止，或由工作流总时限自动停止并保留检查点。

## 快速开始（Windows）

要求：Windows PowerShell、Python 3.11+、Node.js 18+ 和 `uv`。如果系统没有 `uv`，项目脚本也会尝试使用 `python -m uv` 或 `py -m uv`。

```powershell
Copy-Item .env.example .env
# 按需编辑 .env；在线模式至少填写 AI_API_KEY 和 AI_MODEL
.
\scripts\setup.ps1
.\start.ps1
```

`start.ps1` 会启动前后端并打开浏览器。也可以分别运行：

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1
```

默认地址：

- 前端：http://127.0.0.1:5173
- 后端：http://127.0.0.1:8017
- Swagger API 文档：http://127.0.0.1:8017/docs
- 健康检查：http://127.0.0.1:8017/api/health

## 环境变量

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `AI_API_KEY` | 否 | OpenAI 兼容接口密钥；为空时使用本地模板 |
| `AI_BASE_URL` | 否 | 默认 `https://api.openlux.ai/v1` |
| `AI_MODEL` | 在线模式必需 | 在线模型名称，例如 `gpt-5.6-luna` |
| `MPT_PEXELS_API_KEY` | 成片时可选 | MoneyPrinterTurbo 素材服务 |
| `BACKEND_PORT` | 否 | 默认 `8017` |
| `NEWS_FETCH_TIMEOUT_SECONDS` | 否 | 热点抓取超时；`0` 表示不限时，默认 `90` |
| `MODEL_TIMEOUT_SECONDS` | 否 | 模型调用超时；`0` 表示不限时，默认 `30` |
| `WORKFLOW_TIMEOUT_SECONDS` | 否 | 完整工作流总时限；`0` 表示不限时，默认 `300` |
| `SOCIALDATAX_API_KEY` | 爆款分析可选 | SocialDataX API Key；从 [SocialDataX API Key 页面](https://socialdatax.com/dashboard/api-keys) 获取 |
| `SOCIALDATAX_BASE_URL` | 否 | 默认 `https://mcp.socialdatax.com` |
| `SOCIALDATAX_TIMEOUT_SECONDS` | 否 | SocialDataX 请求超时；`0` 表示不限时，默认 `60` |
| `TUSHARE_TOKEN` | 否 | 股票数据增强 |
| `TAVILY_API_KEY` / `SERPAPI_KEY` | 否 | 股票新闻增强 |

超时也可以在前端“设置”页修改，保存到 `workspaces/runtime-settings.json`；运行中可在总览页点击“停止任务”。

## API 一览

| API | 用途 |
| --- | --- |
| `GET /api/health`、`GET /api/status` | 健康检查和 AI 模式诊断 |
| `GET /api/agents` | 获取岗位与 Skill 信息 |
| `POST /api/topics/scout` | 扫描热点线索 |
| `POST /api/scripts/generate` | 单独生成脚本 |
| `POST /api/stocks/analyze` | 股票分析 |
| `POST /api/workflows/hot-video` | 执行完整工作流 |
| `GET /api/workflows`、`GET /api/workflows/{id}` | 查询任务 |
| `POST /api/workflows/{id}/resume` | 从失败检查点继续 |
| `POST /api/workflows/{id}/step` | 只执行下一个岗位阶段；创建任务时传 `execution_mode: "step"` 可进入手动模式 |
| `GET/POST /api/workflows/{id}/export`、`POST /api/workflows/import` | 项目导出与导入 |
| `GET/POST /api/video/moneyprinterturbo/*` | 检查并调用剪辑工具 |

## Agent 与 Skill

核心流水线岗位是热点监控员赵爽、爆款分析师星辰、文案助手洛一、视频剪辑员小李和运营大师尤道理。产品经理方舟、程序员阿栈、股票助手林量和心理疗愈师周周作为扩展岗位展示或提供专项能力。

岗位工作区位于 `workspaces/agents/<agent_id>`；每次任务的产物位于 `workspaces/runs/<run_id>/<agent_id>/`，老板摘要位于 `boss/run-summary.json`。

已纳入仓库的专项能力包括：

- `hotspot_monitor`：`news-aggregator-skill`
- `viral_analyst`：SocialDataX 小红书笔记搜索 API（[接口文档](https://socialdatax.com/dashboard/api-docs)）
- `stock_assistant`：`stock-analysis`
- `video_editor`：MoneyPrinterTurbo 官方 Agent Skill
- `operator`：`newmedia-operations`
- `product_manager`：`Product-Manager-Skills`
- `healer`：`mental-health-assistant`

Skill 来源、版本和许可证记录见 [`workspaces/agents/SKILLS.md`](workspaces/agents/SKILLS.md) 与 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。本仓库没有复制 MoneyPrinterTurbo 主项目源码。

## 项目结构

```text
backend/app/             FastAPI、配置、Agent、工作流和外部工具适配
frontend/src/            React/Vite 调度台
scripts/                 安装、开发启动和检查脚本
workspaces/agents/       按岗位隔离的 Skill 与工作区
workspaces/runs/         任务状态和岗位产物
pic/                     项目界面截图
showboard.md             功能、实现边界和验证记录
pyproject.toml           Python 依赖声明
uv.lock                  uv 锁定依赖
```

## 检查与排障

```powershell
.\scripts\check.ps1
uv lock --check
```

如果端口已被其他程序占用，修改 `.env` 中的 `BACKEND_PORT`，并通过前端开发命令传入新的前端端口。设置页可查看项目服务是否运行，并执行后端启动、重启和关闭操作。

## 已知边界

- 真实热点依赖公开来源抓取；网络、来源格式或模型超时都会影响结果。
- SocialDataX 爆款样本依赖有效 API Key 和账户积分；每次小红书笔记搜索按服务商规则计费，未配置时分析阶段会明确降级为待验证假设。
- `verified` 只表示当前实现完成了来源结构和域名数量检查，不等于人工事实核查或编辑审核。
- 工作流是本地单机原型，尚未提供数据库、账号权限、队列服务、并发治理和线上监控。
- MoneyPrinterTurbo 真实成片还依赖其上游运行环境、模型和素材服务，生成失败时仍可保留剪辑方案。
- 项目没有真实运营样本，因此不声称已经验证完播率、CTR、互动率、转化率或 ROI。

## 许可与致谢

本项目许可证见 [`LICENSE`](LICENSE)。第三方 Skill 和上游项目按其各自许可证使用，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。项目参考了“一人公司”Agent 分工思路、MoneyPrinterTurbo、Product-Manager-Skills 及相关内容生产 Skill。
