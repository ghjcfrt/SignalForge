# 热讯工坊（SignalForge）

热讯工坊是一个本地运行的 AI 内容生产调度台，把“热点线索 → 事实核查 → 爆款分析 → 脚本 → 剪辑方案 → 运营发布”拆成多个岗位 Agent。项目适合用来验证一人公司式内容生产流程、Agent 分工和结构化产物沉淀。

当前项目是可运行原型，不承诺已经具备生产环境级别的新闻准确率、视频成片成功率或运营效果。

本文先给出快速启动和能力摘要，后半部分补充工作流契约、API 字段、产物恢复和排障细节。

## 目录

- [热讯工坊（SignalForge）](#热讯工坊signalforge)
  - [目录](#目录)
  - [当前能力](#当前能力)
  - [快速开始（Windows）](#快速开始windows)
  - [环境变量](#环境变量)
  - [API 一览](#api-一览)
  - [Agent 与 Skill](#agent-与-skill)
  - [项目结构](#项目结构)
  - [检查与排障](#检查与排障)
  - [已知边界](#已知边界)
  - [许可与致谢](#许可与致谢)
  - [系统要求与安装细节](#系统要求与安装细节)
  - [三种工作流执行模式](#三种工作流执行模式)
  - [来源、核验与爆款分析边界](#来源核验与爆款分析边界)
  - [独立员工工作台](#独立员工工作台)
  - [API 参考](#api-参考)
  - [产物、日志与项目导入导出](#产物日志与项目导入导出)
  - [检查、测试与验证](#检查测试与验证)
  - [排障手册](#排障手册)
    - [找不到 uv、Python 或 Node](#找不到-uvpython-或-node)
    - [端口被占用](#端口被占用)
    - [页面显示“本地模板”](#页面显示本地模板)
    - [热点扫描失败或没有已核验候选](#热点扫描失败或没有已核验候选)
    - [SocialDataX 没有样本或返回错误](#socialdatax-没有样本或返回错误)
    - [MoneyPrinterTurbo 无法成片](#moneyprinterturbo-无法成片)
    - [股票数据不完整](#股票数据不完整)
  - [实现边界与安全说明](#实现边界与安全说明)

## 当前能力

- 控制台：执行完整的热视频工作流，查看阶段状态、热点和岗位产物。
- 热点雷达：调用 `news-aggregator-skill` 抓取公开来源，并要求模型基于来源整理选题。
- 真实性门禁：至少两个不同域名的独立来源交叉验证后，热点才会进入后续生产阶段；否则任务停止并保留失败检查点。
- 爆款分析：针对已核验选题调用 SocialDataX 小红书笔记搜索，按高互动样本拆解标题、内容结构和传播钩子；该接口只用于爆款分析，不参与新闻抓取或事实核验。
- 文案助手：在完整流水线或员工独立工作台中生成短视频脚本。
- 股票分析：调用 `stock-analysis` Skill 生成股票/财经分析，可选接入 Tushare、Tavily、SerpApi。
- 剪辑队列：生成 MoneyPrinterTurbo 剪辑方案，并可调用其 helper 尝试真实成片。
- 互动回复、员工、设置：展示岗位信息、评论处理样例、AI 状态、超时设置、项目导入导出和本地服务控制；员工独立工作台的最新产物也会随当前项目导出，并在导入后恢复。
- 无 Key 回退：没有 `AI_API_KEY` 时仍可启动并验证本地模板、接口和前端流程；需要实时热点和在线模型时必须配置 Key。
- 任务持久化：运行状态会写入 `workspaces/runs/<run_id>/run-state.json`，服务重启后会尝试恢复已保存的任务。
- 阶段化执行：完整模式在后台逐阶段执行并实时保存；控制台也可以逐个岗位执行下一步，失败后从当前阶段继续。
- 执行日志：每个任务会生成 `run.log`，界面同步展示阶段、错误类型和详细原因。
- 爆款分析可切换 SocialDataX 或手写策略；SocialDataX 模式会先取高互动排行，再按已核验选题搜索样本，视频样本会尝试提取口播。
- 热点候选会先完成全量排序和来源核验，再选择进入后续生产的候选；运行中可以手动停止，或由工作流总时限自动停止并保留检查点。

## 快速开始（Windows）

要求：Windows PowerShell、Python 3.11+、Node.js 18+ 和 `uv`。如果系统没有 `uv`，项目脚本也会尝试使用 `python -m uv` 或 `py -m uv`。

```powershell
Copy-Item .env.example .env
# 按需编辑 .env；在线模式至少填写 AI_API_KEY 和 AI_MODEL
.\scripts\setup.ps1
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
| `FRONTEND_PORT` | 否 | Vite 前端端口，默认 `5173` |
| `NEWS_FETCH_TIMEOUT_SECONDS` | 否 | 热点抓取超时；`0` 表示不限时，默认 `90` |
| `MODEL_TIMEOUT_SECONDS` | 否 | 模型调用超时；`0` 表示不限时，默认 `30` |
| `WORKFLOW_TIMEOUT_SECONDS` | 否 | 完整工作流总时限；`0` 表示不限时，默认 `300`（视频剪辑员渲染阶段始终不限时） |
| `NEWS_SOURCE_MODE` | 否 | 热点来源模式：`live`、`fixture` 或 `live_then_fixture` |
| `NEWS_RSS_FEEDS` | 否 | 可配置 RSS，格式为 `名称|URL`，多个用逗号分隔 |
| `NEWS_FIXTURE_PATH` | 否 | 热点离线 fixture JSON 路径，默认 `tests/fixtures/hotspots.json` |
| `SOCIALDATAX_API_KEY` | 爆款分析可选 | SocialDataX API Key；从 [SocialDataX API Key 页面](https://socialdatax.com/dashboard/api-keys) 获取 |
| `SOCIALDATAX_BASE_URL` | 否 | 默认 `https://mcp.socialdatax.com` |
| `SOCIALDATAX_TIMEOUT_SECONDS` | 否 | SocialDataX 请求超时；`0` 表示不限时，默认 `60` |
| `TUSHARE_TOKEN` | 否 | 股票数据增强 |
| `TAVILY_API_KEY` / `SERPAPI_KEY` | 否 | 股票新闻增强 |
| `STOCK_FETCH_RETRIES` / `STOCK_CACHE_TTL_SECONDS` | 否 | 股票数据有限重试次数和缓存时长 |

超时也可以在前端“设置”页修改，保存到 `workspaces/runtime-settings.json`；运行中可在控制台点击“停止任务”。

## API 一览

| API | 用途 |
| --- | --- |
| `GET /api/health`、`GET /api/status` | 健康检查和 AI 模式诊断 |
| `GET /api/agents` | 获取岗位与 Skill 信息 |
| `POST /api/topics/scout` | 扫描热点线索 |
| `POST /api/stocks/analyze` | 股票分析 |
| `GET /api/stocks/health` | 股票数据源健康状态、重试和缓存配置 |
| `POST /api/workflows/hot-video` | 执行完整工作流 |
| `GET /api/workflows`、`GET /api/workflows/{id}` | 查询任务 |
| `POST /api/workflows/{id}/resume` | 从失败检查点继续 |
| `POST /api/workflows/{id}/step` | 只执行下一个岗位阶段；创建任务时传 `execution_mode: "step"` 可进入逐步模式 |
| `GET/POST /api/workflows/{id}/export`、`POST /api/workflows/import` | 项目导出与导入 |
| `GET/POST /api/video/moneyprinterturbo/*` | 检查并调用剪辑工具 |

更完整的接口和字段说明见下方“API 参考”。

## Agent 与 Skill

核心流水线岗位是热点监控员、爆款分析师、文案助手、视频剪辑员和运营大师。产品经理、程序员、股票助手和心理疗愈师作为扩展岗位展示或提供专项能力。

岗位工作区位于 `workspaces/agents/<agent_id>`；每次任务的产物位于 `workspaces/runs/<run_id>/<agent_id>/`，老板摘要位于 `boss/run-summary.json`。

已纳入仓库的专项能力包括：

- `hotspot_monitor`：`news-aggregator-skill`
- `viral_analyst`：SocialDataX 搜索 API（[接口文档](https://socialdatax.com/dashboard/api-docs)）
- `stock_assistant`：`stock-analysis`
- `video_editor`：MoneyPrinterTurbo 官方 Agent Skill
- `operator`：`newmedia-operations`
- `product_manager`：`Product-Manager-Skills`
- `healer`：`mental-health-assistant`

Skill 来源、版本和许可证记录见 [`workspaces/agents/SKILLS.md`](workspaces/agents/SKILLS.md) 与 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。本仓库没有复制 MoneyPrinterTurbo 主项目源码。

## 第三方清单

下表列出本项目直接使用、随仓库提供或运行时调用的主要第三方组件。完整的归属、许可证、分发注意事项和配置项见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

| 类别 | 第三方 | 在本项目中的用途 | 许可证/说明 |
| --- | --- | --- | --- |
| 随仓库提供的 Skill | [`news-aggregator-skill`](https://github.com/cclank/news-aggregator-skill) | 微博、华尔街见闻、BBC、Reuters 等热点抓取 | 上游 README 声称 MIT；仓库未提供独立 LICENSE，分发前需确认 |
| 随仓库提供的 Skill | [`moneyprinterturbo-video`](https://github.com/harry0703/MoneyPrinterTurbo/tree/main/docs/skill) | 剪辑方案和真实视频成片 helper | MIT；仓库内保留 `LICENSE.MoneyPrinterTurbo`，未复制主项目源码 |
| 随仓库提供的 Skill | [`stock-analysis`](https://github.com/liusai0820/Stock-Analysis-Skill) | A 股、港股、美股数据与分析 | 上游 README 声称 MIT；仓库未提供独立 LICENSE，分发前需确认 |
| 随仓库提供的 Skill | [`Product-Manager-Skills`](https://github.com/deanpeters/Product-Manager-Skills) | 产品发现、需求和竞品分析 | CC BY-NC-SA 4.0，需署名、非商业使用并遵守相同方式共享 |
| 随仓库提供的 Skill | `newmedia-operations` | 内容运营、发布、互动和复盘 | 当前元数据未声明独立许可证，不得默认按 MIT 分发 |
| 随仓库提供的 Skill | `mental-health-assistant` | 情绪支持与心理话题安全边界 | 当前元数据未声明独立许可证，不得默认按 MIT 分发 |
| 运行时在线服务 | [OpenAI 兼容 API](https://api.openlux.ai/v1) | 在线模型生成和分析 | 服务条款、计费和内容政策以实际服务商为准 |
| 运行时在线服务 | [SocialDataX](https://socialdatax.com/dashboard/api-docs) | 小红书公开笔记样本和口播提取 | 只用于爆款分析；按服务商规则计费，不是新闻源或事实核验器 |
| 运行时在线服务 | [Pexels API](https://www.pexels.com/api/) | MoneyPrinterTurbo 素材搜索 | 需遵守 Pexels API 条款及素材许可 |
| 运行时数据源 | BBC RSS、微博、华尔街见闻、Reuters | 热点候选来源 | 内容版权归各来源及原作者，转载须遵守来源条款 |
| 运行时数据源 | Tushare、Tavily、SerpApi | 股票行情和新闻增强 | 均为可选服务，受各自配额和服务条款约束 |
| Python 依赖 | FastAPI、Uvicorn、OpenAI SDK、httpx、Pydantic、python-dotenv、uv | 后端 API、配置、网络和依赖管理 | 具体版本以 `pyproject.toml`/`uv.lock` 及各自上游许可证为准 |
| Python 依赖 | AKShare、yfinance、efinance、curl-cffi、protobuf、python-multipart | 股票数据、HTTP、协议和上传解析 | 具体许可证见各包上游项目 |
| 前端依赖 | React、React DOM、Vite、TypeScript、Lucide React | 调度台 UI、构建和图标 | 具体版本以 `frontend/package.json` 和锁文件为准 |
| 前端依赖 | react-markdown、remark-gfm、Playwright | Markdown 渲染和端到端测试 | 具体许可证见各 npm 包和上游项目 |

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

## 系统要求与安装细节

项目当前以 Windows 本地运行作为主要验证环境，要求：

- Windows PowerShell（Windows PowerShell 5.1 或 PowerShell 7 均可）
- Python 3.11+
- Node.js 18+
- [`uv`](https://docs.astral.sh/uv/)
- 可选：可访问公开 RSS/新闻源的网络、OpenAI 兼容模型 Key、SocialDataX Key、Pexels Key

`scripts/setup.ps1` 会先执行 `uv sync`，再进入 `frontend` 执行 `npm install`。找不到独立的 `uv` 命令时，脚本会依次尝试 `python -m uv` 和 `py -m uv`。Python 依赖声明在 `pyproject.toml`，锁定在 `uv.lock`；前端依赖锁定在 `frontend/package-lock.json` 和 `frontend/pnpm-lock.yaml`。

`start.ps1` 会检查后端和前端端口是否被其他程序占用，只接管能确认属于本项目的进程，然后启动：

| 服务 | 默认地址 |
| --- | --- |
| React/Vite 调度台 | http://127.0.0.1:5173 |
| FastAPI 后端 | http://127.0.0.1:8017 |
| Swagger/OpenAPI | http://127.0.0.1:8017/docs |
| ReDoc | http://127.0.0.1:8017/redoc |
| 健康检查 | http://127.0.0.1:8017/api/health |

需要换端口时，在启动前设置 `BACKEND_PORT` 或 `FRONTEND_PORT`：

```powershell
$env:BACKEND_PORT = "18017"
$env:FRONTEND_PORT = "15173"
.\start.ps1
```

## 三种工作流执行模式

`POST /api/workflows/hot-video` 的 `execution_mode` 有三种取值：

| 模式 | 行为 | 推荐用途 |
| --- | --- | --- |
| `auto` | 后台依次执行五个阶段，阶段完成即写入检查点 | 一键跑完整流程 |
| `step` | 创建后只执行一个阶段，阶段结束后暂停 | 逐步审核、及时止损 |
| `manual` | 只创建任务和初始检查点，不启动后台执行 | 先准备输入，稍后明确启动 |

阶段顺序固定为 `hotspot_monitor → viral_analyst → copywriter → video_editor → operator`。手动模式下可以先执行热点监控，查看候选的来源、发布时间和核验结果，再通过“执行下一步”继续。每个阶段卡片也支持重跑；指定重跑阶段时会保留上游检查点并重置该阶段及下游产物。

工作流状态包括 `queued`、`running`、`paused`、`completed`、`failed`。用户停止任务、总时限到期或阶段异常后会保留 `resumable` 检查点，可使用“继续”或 `/resume` 接口恢复。后端启动时会扫描已有 `run-state.json` 并加载任务记录。

## 来源、核验与爆款分析边界

热点监控的来源优先级如下：

1. `news-aggregator-skill` 的微博、华尔街见闻、BBC、Reuters 等公开源；
2. Skill 不存在时的内置 RSS 抓取器；
3. `live_then_fixture` 模式下，实时抓取失败后的 `tests/fixtures/hotspots.json`。

热点候选会先完成全量排序、去重和来源补充，然后再交给模型整理。一个候选必须同时满足“至少两个来源”和“至少两个独立发布域名”才会标记为 `verified`；同一个站点的多个页面不算跨域核验。`verified` 只表示代码完成了 URL、发布时间、来源主张和域名数量检查，发布前仍应人工打开原文。

爆款分析有两条路径：

- `socialdatax`：需要 `SOCIALDATAX_API_KEY` 和账户积分。系统先取平台高互动排行，再按已核验选题搜索样本，并对视频笔记尽力提取口播。点赞、收藏、评论、分享只用于同平台样本比较，不能跨平台直接比较，也不能据此声称平台总体趋势。
- `manual`：必须填写具体样本、数据或分析结论；空输入会明确失败。手写模式不会发起 SocialDataX 请求。

爆款分析师输出“施工图”（角度、核心观点、标题结构、开头策略、内容顺序、事实清单、禁用表达和风格），文案助手负责最终标题和脚本成稿。没有样本库时，系统只接受用户提供的样本，不会把模型记忆包装成数据规律。

## 独立员工工作台

左侧员工页是独立调用，不会自动加入流水线。每次调用都有独立的 `timeout_seconds`，并写入独立的 `agent-<agent_id>-<suffix>` 运行目录。可通过 `project_run_id` 把最新独立结果绑定到某个项目，使它进入项目导出范围。

核心员工的输入重点：

| Agent | 输入与产物 |
| --- | --- |
| `hotspot_monitor` | 方向、受众；热点报告 |
| `viral_analyst` | 主题 + SocialDataX 或手写分析依据；爆款分析规范 |
| `copywriter` | 主题、角度、时长、受众；带时间轴脚本 |
| `video_editor` | 主题或完整脚本、画幅和剪辑要求；剪辑执行单/成片结果 |
| `operator` | 选题或脚本；发布、互动和复盘方案 |
| `stock_assistant` | 逗号分隔的 A 股/港股/美股代码或名称；股票分析报告 |
| `product_manager`、`programmer`、`healer` | 岗位任务描述；独立 Markdown 产物 |

## API 参考

完整请求字段和响应模型以 http://127.0.0.1:8017/docs 为准。常用接口如下：

核心请求对象：

| 对象 | 字段 | 约束/说明 |
| --- | --- | --- |
| `TopicSeed` | `domain`, `brief`, `audience` | 领域、老板方向和目标受众；均为字符串 |
| `TopicSeed` | `duration_seconds` | 30–240 秒，默认 110 |
| `TopicSeed` | `video_aspect` | `vertical` 或 `horizontal`，默认 `vertical` |
| `ViralAnalysisConfig` | `source` | `socialdatax` 或 `manual` |
| `ViralAnalysisConfig` | `enabled` | 是否执行爆款分析阶段，默认 `true` |
| `ViralAnalysisConfig` | `manual_content` | 手写模式的样本/数据/结论，最长 30,000 字符 |
| `RunAgentRequest` | `agent_id`, `prompt` | 路径中的员工 ID 必须与请求体一致 |
| `RunAgentRequest` | `settings` | 岗位专属键值，例如股票、脚本、画幅和输出目录 |
| `RunAgentRequest` | `timeout_seconds` | 独立工作台超时；0 表示不限时，默认 300 |
| `RunAgentRequest` | `project_run_id` | 可选；绑定后独立产物进入该项目导出范围 |

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务健康检查 |
| `GET` | `/api/status` | AI Key、模型、Base URL、运行模式和诊断 |
| `GET/PUT` | `/api/settings/timeouts` | 读取/保存热点、模型、工作流超时；`0` 表示不限时 |
| `GET/PUT` | `/api/settings/output-directories` | 视频和运营产物目录 |
| `GET/PUT` | `/api/settings/env` | 读取脱敏配置或更新 `.env`；密钥只返回掩码预览 |
| `GET` | `/api/agents` | Agent 与 Skill 信息 |
| `GET` | `/api/agents/{agent_id}/logs` | 最近 100 条独立任务日志 |
| `POST` | `/api/topics/scout` | 单独扫描热点候选 |
| `POST` | `/api/stocks/analyze` | 股票分析；`days` 范围 30–365 |
| `GET` | `/api/stocks/health` | 股票库、凭据、重试和缓存状态 |
| `POST` | `/api/agents/{agent_id}/run` | 独立运行员工 |
| `POST` | `/api/workflows/hot-video` | 创建完整工作流 |
| `GET` | `/api/workflows`、`/api/workflows/{run_id}` | 列表/详情 |
| `POST` | `/api/workflows/{run_id}/step` | 执行下一阶段或指定阶段重跑 |
| `POST` | `/api/workflows/{run_id}/resume` | 恢复可继续任务 |
| `POST` | `/api/workflows/{run_id}/cancel` | 停止后台任务并保留检查点 |
| `GET` | `/api/workflows/{run_id}/export` | 导出 `signalforge-project` JSON |
| `POST` | `/api/workflows/import` | 上传项目 JSON 并恢复为新任务 |
| `GET` | `/api/artifacts/preview?path=...` | 预览工作区内图片产物 |
| `GET` | `/api/video/moneyprinterturbo/status` | 检查视频 Skill、helper 和缺少的配置 |
| `POST` | `/api/video/moneyprinterturbo/run` | 调用视频 helper 尝试生成成片 |

前端 Vite 还提供本机服务控制路由（这些路由不是 FastAPI `/api` 路由）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/local-control/status` | 查看前后端端口、进程归属和可执行操作 |
| `POST` | `/local-control/backend/start` | 启动当前项目后端 |
| `POST` | `/local-control/backend/stop` | 停止当前项目后端 |
| `POST` | `/local-control/backend/restart` | 重启当前项目后端 |
| `POST` | `/local-control/frontend/stop` | 关闭当前 Vite 进程 |
| `POST` | `/local-control/shutdown` | 关闭前后端 |

这些控制接口只用于同一台机器上的本地调度；不要把 Vite 开发服务器暴露到公网。

创建手动任务并执行下一步的 PowerShell 示例：

```powershell
$body = @{
  execution_mode = "manual"
  seed = @{
    domain = "AI 工具"
    brief = "近期影响普通创作者的产品和模型变化"
    audience = "关注 AI 工具的一线创作者"
    duration_seconds = 90
    video_aspect = "vertical"
  }
  viral_analysis = @{
    source = "manual"
    enabled = $true
    manual_content = "先讲受众影响，再讲已确认事实。"
  }
} | ConvertTo-Json -Depth 6
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8017/api/workflows/hot-video -ContentType "application/json" -Body $body
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8017/api/workflows/$($run.id)/step"
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8017/api/workflows/$($run.id)"
```

导出项目：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8017/api/workflows/$($run.id)/export" |
  ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 signalforge-project.json
```

## 产物、日志与项目导入导出

完整任务的目录结构通常如下：

```text
workspaces/runs/<run_id>/
├── run-state.json                 # 完整任务状态和恢复信息
├── run.log                        # JSONL 工作流日志
├── hotspot_monitor/hotspot_monitor.md
├── viral_analyst/viral_analyst.md
├── copywriter/copywriter.md
├── video_editor/video_editor.md
├── operator/operator.md
└── boss/run-summary.json          # 完成后的老板摘要
```

独立员工日志位于 `workspaces/agent-logs/<agent_id>/agent.log`，独立产物位于 `workspaces/runs/agent-<agent_id>-<suffix>/`。导出接口包含热点、阶段状态、日志、流水线产物和 `standalone_outputs`；导入后会生成新的 `imported-...` 任务 ID。导入只恢复项目数据，不会自动重新发起外部网络请求。

## 检查、测试与验证

请始终从仓库根目录运行，避免相对路径和系统 Python 依赖问题：

```powershell
# 后端 compileall + 前端 TypeScript/Vite build
.\scripts\check.ps1

# 依赖锁文件
uv lock --check

# 后端 API/持久化测试
uv run python -m unittest discover -s tests -p "test_*.py"

# 不依赖真实模型和新闻网络的五阶段确定性 smoke
uv run python scripts/smoke_workflow.py

# 后端已运行时的 HTTP 冒烟
uv run python scripts/smoke_api.py

# 前端 Playwright（需要前端已启动）
Push-Location frontend
npm run test:e2e
Pop-Location
```

不要在 `frontend` 目录运行 `python -m compileall backend`；应回到仓库根目录运行 `.\scripts\check.ps1`，或使用 `.venv\Scripts\python.exe` / `uv run`。

## 排障手册

### 找不到 uv、Python 或 Node

确认 `uv --version`、`python --version`、`node --version` 和 `npm --version` 可执行，重新打开 PowerShell 后再运行 `.\scripts\setup.ps1`。脚本不会自动安装 Node.js。

### 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 8017,5173 -State Listen
```

确认占用者后设置新的 `BACKEND_PORT`/`FRONTEND_PORT`。`start.ps1` 不会强行终止无法确认归属的进程。

### 页面显示“本地模板”

访问 `/api/status` 查看 `diagnostic`。常见原因是 `AI_API_KEY` 为空、Base URL 不可达或模型名称不可用。本地模板仍可用于构建、接口和离线工作流验证，但不是实时模型结果。

### 热点扫描失败或没有已核验候选

检查网络、`NEWS_SOURCE_MODE`、RSS 地址和 fixture 文件。先设为 `fixture` 验证流程，再切回 `live`；不要把 fixture 内容直接当作当天新闻发布。

### SocialDataX 没有样本或返回错误

确认 API Key、账户积分、Base URL 和服务商业务码。HTTP 200 不一定代表业务成功；429 时应遵守响应中的 `Retry-After`。没有样本时系统会输出待验证假设，不会编造互动数据。

### MoneyPrinterTurbo 无法成片

调用 `/api/video/moneyprinterturbo/status` 查看 `missing_env`，通常需要 `AI_API_KEY`、`AI_BASE_URL` 和 `MPT_PEXELS_API_KEY`。成片过程可能包含依赖安装、素材下载、TTS 和编码，耗时不受工作流规划总时限强制终止；即使失败，剪辑方案和 helper 返回的日志路径仍会保留。

### 股票数据不完整

调用 `/api/stocks/health` 查看库和凭据。结果会标记 `ok`、`partial` 或 `unavailable`，并附带来源状态和免责声明；缺少数据时不会用模型记忆补价格或新闻。

## 实现边界与安全说明

- 热点来源是公开网络、配置的 RSS 或本地 fixture；网络和来源异常必须在日志中保留，不使用模型记忆填充事实。
- SocialDataX 是爆款分析的数据访问层，不是新闻源、事实核验器或自动爆款预测器。
- 项目是本地单机原型，未提供数据库、账号权限、队列服务、并发治理、自动登录、自动发布或线上监控。
- `verified` 不等于人工事实核查；发布前应打开原文、核对时间和上下文。
- 股票助手输出仅供参考，不构成投资建议；心理疗愈师不能替代医疗、诊断或危机干预服务。
- 设置接口只返回密钥掩码预览；不要提交 `.env`、私密配置或含凭据的日志。
- 没有真实运营样本，因此不声称已验证完播率、CTR、互动率、转化率或 ROI。
