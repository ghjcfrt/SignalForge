# 热讯工坊

热讯工坊是一个从 0 搭建的“一人公司”项目：你是老板，多个 AI 员工各司其职，围绕“热点监控 -> 爆款分析 -> 脚本撰写 -> 视频剪辑方案 -> 运营发布”完成短视频内容生产。

项目不依赖 Qclaw。后端使用 Python + FastAPI，Python 依赖通过 `uv` 安装到 `.venv` 虚拟环境；前端使用 React + Vite。

## AI 接口

后端默认使用 OpenAI 兼容接口：

- AI 密钥环境变量：`AI_API_KEY`
- Base URL：`https://api.wlai.vip/v1`
- Model：`AI_MODEL` 非必填；留空时由 AI 中转站自动选择

没有配置 key 时，项目仍可运行，会使用本地模板输出，方便先验证工作流。

## 快速启动

PowerShell：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入 AI_API_KEY

.\scripts\setup.ps1
.\start.ps1
```

另开一个 PowerShell：

```powershell
 （无需再单独启动前端，`start.ps1` 会自动启动前后端。）
```

默认地址：

- 前端：http://127.0.0.1:5173
- 后端：http://127.0.0.1:8017
- API 文档：http://127.0.0.1:8017/docs

## Agent 员工

| 职位       | 员工   | 负责内容                                                      |
| ---------- | ------ | ------------------------------------------------------------- |

| 热点监控员 | 赵爽   | 搜集 AI 圈、B站/社媒热点，沉淀选题                            |
| 爆款分析师 | 星辰   | 分析传播钩子、争议点和内容结构                                |
| 文案助手   | 洛一   | 生成 90-120 秒短视频脚本                                      |
| 视频剪辑员 | 小李   | 使用 MoneyPrinterTurbo 生成配音、素材、字幕、背景音乐与短视频 |
| 运营大师   | 尤道理 | 生成标题、封面文案、发布时间和互动策略                        |
| 产品经理   | 方舟   | 做产品调研、竞品和需求总结                                    |
| 程序员     | 阿栈   | 配合产品经理实现工具和自动化                                  |
| 股票助手   | 林量   | 查看股票相关信息和市场摘要                                    |
| 心理疗愈师 | 周周   | 情感话题沟通疏导                                              |

每个 Agent 都有独立目录：`workspaces/agents/<agent_id>`。每次工作流运行会写入 `workspaces/runs/<run_id>/<agent_id>`，避免不同员工“串台”。

## 剪辑 Skill：MoneyPrinterTurbo

小李的剪辑 Skill 已安装到：

```text
workspaces/agents/video_editor/skills/moneyprinterturbo-video/
```

该目录包含：

- `SKILL.md`：MoneyPrinterTurbo 官方 Agent Skill
- `mpt_agent.py`：官方 helper，用于安装/调用 MoneyPrinterTurbo CLI
- `README.MoneyPrinterTurbo.md`：上游 README 备份
- `LICENSE.MoneyPrinterTurbo`：上游 MIT License

出处：

- 上游项目：[harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)
- 官方 Skill：[docs/skill/SKILL.md](https://github.com/harry0703/MoneyPrinterTurbo/tree/main/docs/skill)
- License：MIT

默认运行方式：

```powershell
Set-Location workspaces\agents\video_editor\skills\moneyprinterturbo-video
python -m uv run --no-project --python 3.11 python mpt_agent.py --subject "视频主题或脚本"
```

真实成片需要配置：

```text
AI_API_KEY=<AI 服务 API Key>
AI_BASE_URL=https://api.wlai.vip/v1
AI_MODEL=
MPT_PEXELS_API_KEY=<Pexels API Key>
```

后端也提供了接口：

- `GET /api/video/moneyprinterturbo/status`
- `POST /api/video/moneyprinterturbo/run`

## 其它 Skill

除 MoneyPrinterTurbo 外，其它岗位 Skill 已按员工独立 Workspace 安装。完整登记见 `workspaces/agents/SKILLS.md`。

| 岗位       | Skill                       | 安装路径                                                             | 来源与状态                                                                                                |
| ---------- | --------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 热点监控员 | `bilibili-search`         | `workspaces/agents/hotspot_monitor/skills/bilibili-search/`        | ClawHub/Volces，owner`excalibursssooo`，version `0.1.0`，MIT-0                                        |
| 运营大师   | `newmedia-operations`     | `workspaces/agents/operator/skills/newmedia-operations/`           | ClawHub/Volces，owner`swcxy12315`，version `1.0.0`，上游未声明许可证                                  |
| 产品经理   | `Product-Manager-Skills`  | `workspaces/agents/product_manager/skills/Product-Manager-Skills/` | [deanpeters/Product-Manager-Skills](https://github.com/deanpeters/Product-Manager-Skills)，CC BY-NC-SA 4.0 |
| 心理疗愈师 | `mental-health-assistant` | `workspaces/agents/healer/skills/mental-health-assistant/`         | ClawHub/Volces，owner`ttoooong`，version `2.1.0`，上游未声明许可证                                    |

当前对外展示和默认剪辑链路只使用 MoneyPrinterTurbo。

股票助手已安装 `stock-analysis`，接口为 `POST /api/stocks/analyze`；涉及财经、股票或股票新闻时使用该 Skill。可选配置 `TUSHARE_TOKEN`、`TAVILY_API_KEY`、`SERPAPI_KEY` 增强数据质量和新闻抓取。爆款分析师使用 `SpaceZephyr/creator-buddy` 的 `space-xhs-hotspot` 子 Skill；文案助手和程序员按设计不安装单独 Skill。

新闻真实性边界：热点线索必须同时具备至少两个相互独立的来源、来源 URL、各自发布时间、对同一事实的交叉验证说明，并标记为 `verified`，才能进入后续爆款分析、脚本和发布流程。相同转载链、单一来源或只有模型推测的内容都不算多方验证；未满足条件时系统只展示“未核验线索”，并停止后续生产链路。

## 项目结构

```text
backend/
  app/
    main.py              FastAPI 入口
    agents.py            AI 员工定义
    config.py            环境配置
    llm.py               OpenAI 兼容客户端
    workflows.py         热点短视频工作流
frontend/
  src/
    App.tsx              调度台主界面
    api.ts               后端 API 封装
    data.ts              UI 静态元数据
    styles.css           视觉系统
scripts/
  setup.ps1              uv + npm 依赖安装
  dev-backend.ps1        uv 虚拟环境中启动后端
  dev-frontend.ps1       启动前端
```

## 致谢

参考了作者“一人公司”的 Agent 分工思路，以及以下开源项目的方向：

- [B站参考视频：BV1ZcDsBxEQe](https://www.bilibili.com/video/BV1ZcDsBxEQe/)
- [作者博客：Qclaw 超简单 AI 一人公司教程](https://guantou.site/archives/qclawchao-jian-dan-aiyi-ren-gong-si-jiao-cheng-re-dian-xuan-ti-jiao-ben-jian-ji-quan-bao-liao)
- [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)：剪辑员已安装其官方 Agent Skill，见 `workspaces/agents/video_editor/skills/moneyprinterturbo-video/`
- [deanpeters/Product-Manager-Skills](https://github.com/deanpeters/Product-Manager-Skills)：产品经理 Skill
- ClawHub/Volces Skill：`bilibili-search`、`newmedia-operations`、`mental-health-assistant`

本仓库没有复制 MoneyPrinterTurbo 主项目源码；当前仅保存其官方 Agent Skill、helper、README 备份与 MIT License。helper 在真实生成视频时会通过 `uv` 安装和调用 MoneyPrinterTurbo。
## Local deployment

Requirements: Windows PowerShell, Python 3.11+, Node.js 18+, and `uv`.

For a fresh checkout, run `Copy-Item .env.example .env`, configure `.env` if needed, then run `.\scripts\setup.ps1` once. After installation, run `.\start.ps1` from the repository root to start both services and open the frontend automatically.

Default endpoints: frontend `http://127.0.0.1:5173`, backend `http://127.0.0.1:8017`, API docs `http://127.0.0.1:8017/docs`.
