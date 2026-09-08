# 第三方声明

本文件说明热讯工坊（SignalForge）使用、打包或调用的第三方项目、Skill、库和在线服务。

## 1. 许可范围

根目录 [`LICENSE`](LICENSE) 中的 MIT 许可证只适用于 SignalForge 自有代码，不会自动覆盖任何第三方内容。第三方项目仍由其原作者保留著作权，并继续适用各自的许可证、服务条款和使用限制。

仓库内的第三方文件应与其上游说明和许可证一起保留。仅因为某个目录位于本仓库中，并不意味着该内容被重新许可为 MIT，也不代表可以脱离上游许可证进行商业分发。

## 2. 随仓库提供的第三方 Skill

| Skill / 项目 | 用途 | 仓库路径 | 上游来源 | 许可证或当前状态 |
|---|---|---|---|---|
| `news-aggregator-skill` | 抓取微博、华尔街见闻、BBC、Reuters 等公开热点来源 | `workspaces/agents/hotspot_monitor/skills/news-aggregator-skill/` | [cclank/news-aggregator-skill](https://github.com/cclank/news-aggregator-skill) | 上游 README 声称 MIT；当前 checkout 没有独立 LICENSE 文件。分发前应向维护者确认许可，并保留上游 README |
| `moneyprinterturbo-video` | 调用 MoneyPrinterTurbo 生成配音、素材、字幕和视频 | `workspaces/agents/video_editor/skills/moneyprinterturbo-video/` | [MoneyPrinterTurbo Agent Skill](https://github.com/harry0703/MoneyPrinterTurbo/tree/main/docs/skill) | MIT；本仓库随附 [`LICENSE.MoneyPrinterTurbo`](workspaces/agents/video_editor/skills/moneyprinterturbo-video/LICENSE.MoneyPrinterTurbo) 和上游说明。这里没有复制 MoneyPrinterTurbo 主项目源码 |
| `stock-analysis` | 获取 A 股、港股、美股数据并生成股票分析 | `workspaces/agents/stock_assistant/skills/stock-analysis/` | [liusai0820/Stock-Analysis-Skill](https://github.com/liusai0820/Stock-Analysis-Skill) | 上游 README 声称 MIT；当前 checkout 没有独立 LICENSE 文件。分发前应向维护者确认许可，并保留上游 README |
| `Product-Manager-Skills` | 产品发现、需求澄清、竞品分析和路线图 | `workspaces/agents/product_manager/skills/Product-Manager-Skills/` | [deanpeters/Product-Manager-Skills](https://github.com/deanpeters/Product-Manager-Skills) | CC BY-NC-SA 4.0；仓库内保留上游 [`LICENSE`](workspaces/agents/product_manager/skills/Product-Manager-Skills/LICENSE)。须署名，禁止未经许可的商业使用，并遵守相同方式共享要求 |
| `newmedia-operations` | 行业分析、竞品分析、内容运营和互动策略 | `workspaces/agents/operator/skills/newmedia-operations/` | ClawHub/Volces，owner `swcxy12315`，version `1.0.0` | 当前仓库元数据没有提供独立许可证；不得假定可以按 MIT 分发，应取得上游授权 |
| `mental-health-assistant` | 情绪支持、危机识别和心理话题安全边界 | `workspaces/agents/healer/skills/mental-health-assistant/` | ClawHub/Volces，owner `ttoooong`，version `2.1.0` | 当前仓库元数据没有提供独立许可证；不得假定可以按 MIT 分发，应取得上游授权 |

文案助手和程序员目前使用项目内置提示词和工作流逻辑，没有单独安装第三方 Skill。SocialDataX 不是随仓库复制的 Skill，而是运行时在线 API，见下文。

## 3. 运行时在线服务与外部数据源

以下服务不会随仓库分发，但对应功能运行时可能访问它们。是否可用、是否收费、返回数据范围和服务条款以服务商当前页面为准。

| 服务 | 用途 | 配置 | 说明 |
|---|---|---|---|
| [OpenAI 兼容 API](https://api.openlux.ai/v1) | 在线模型生成和结构化分析 | `AI_API_KEY`、`AI_BASE_URL`、`AI_MODEL` | 默认 Base URL 为 OpenLux；也支持其他 OpenAI 兼容服务。未配置时使用本地模板，不代表获得在线模型授权 |
| [SocialDataX](https://socialdatax.com/dashboard/api-docs) | 搜索小红书公开笔记、互动数据和视频口播样本 | `SOCIALDATAX_API_KEY`、`SOCIALDATAX_BASE_URL` | 仅用于爆款分析，不是新闻源或事实核验器；按服务商规则计费并受账户积分、速率限制和服务条款约束 |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 真实视频成片 | `AI_*`、`MPT_PEXELS_API_KEY` | 上游项目为 MIT；本仓库只调用 Agent Skill helper，不包含主项目源码 |
| [Pexels](https://www.pexels.com/api/) | MoneyPrinterTurbo 的素材搜索 | `MPT_PEXELS_API_KEY` | 需遵守 Pexels API 条款、素材许可和速率限制 |
| BBC RSS | 热点 RSS 回退来源 | `NEWS_RSS_FEEDS`（可自定义） | 默认使用 BBC 英文和 BBC 中文 RSS；RSS 内容版权归 BBC 及原作者所有 |
| 微博、华尔街见闻、Reuters 等公开源 | 热点监控 | 由 `news-aggregator-skill` 配置 | 仅抓取公开页面/接口可访问的数据；转载和再发布必须遵守各来源条款 |
| Tushare | 股票数据增强 | `TUSHARE_TOKEN` | 由 `stock-analysis` Skill 按需调用，遵守 Tushare 服务条款 |
| Tavily / SerpApi | 股票新闻增强 | `TAVILY_API_KEY`、`SERPAPI_KEY` | 可选服务；遵守各自 API 条款和配额 |

在线服务的 API Key 存放在本机 `.env`，设置接口只返回掩码预览。不要将密钥、服务商响应中的个人信息或受限内容提交到 Git。

## 4. Python 运行依赖

后端依赖由 [`pyproject.toml`](pyproject.toml) 声明、由 [`uv.lock`](uv.lock) 锁定版本。以下是直接使用的第三方 Python 包：

| 包 | 用途 |
|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | HTTP API 和 OpenAPI 文档 |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI 开发服务器 |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | OpenAI 兼容模型调用 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 读取和更新 `.env` |
| [httpx](https://github.com/encode/httpx) | 异步 HTTP 请求和 RSS/API 访问 |
| [Pydantic](https://github.com/pydantic/pydantic) / [pydantic-settings](https://github.com/pydantic/pydantic-settings) | 请求校验和配置管理 |
| [python-multipart](https://github.com/Kludex/python-multipart) | 项目文件上传解析 |
| [uv](https://github.com/astral-sh/uv) | Python 依赖与隔离环境管理 |
| [curl-cffi](https://github.com/lexiforest/curl_cffi) | 部分数据源的 HTTP 客户端能力 |
| [protobuf](https://github.com/protocolbuffers/protobuf) | 上游数据/客户端运行依赖 |
| [AKShare](https://github.com/akfamily/akshare) | 股票/财经数据 |
| [yfinance](https://github.com/ranaroussi/yfinance) | 美股数据 |
| [efinance](https://github.com/Micro-sheep/efinance) | 股票数据 |

这些包各自拥有上游许可证和依赖树；本文件不替代其许可证文本。实际安装版本以 `uv.lock` 为准。

## 5. 前端运行依赖

前端依赖由 [`frontend/package.json`](frontend/package.json) 声明，版本由 npm/pnpm 锁文件管理：

| 包 | 用途 |
|---|---|
| [React](https://github.com/facebook/react) / `react-dom` | 调度台 UI |
| [Vite](https://github.com/vitejs/vite) | 前端开发服务器和构建 |
| [TypeScript](https://github.com/microsoft/TypeScript) | 类型检查和构建 |
| [Lucide React](https://github.com/lucide-icons/lucide) | 图标 |
| [react-markdown](https://github.com/remarkjs/react-markdown) / [remark-gfm](https://github.com/remarkjs/remark-gfm) | Markdown 产物渲染 |
| [Playwright](https://github.com/microsoft/playwright) | 端到端界面冒烟测试 |
| `@vitejs/plugin-react` | Vite React 插件 |

前端包的具体许可证请以各自 npm 包和上游仓库为准；本仓库未将它们重新许可。

## 6. 维护与分发要求

在重新打包、发布或商业分发本项目之前：

1. 保留本文件、根目录 `LICENSE` 以及各第三方目录中已有的 README/LICENSE 文件。
2. 对标记为“上游未声明许可证”的 Skill，先取得作者的书面授权或移除对应目录和功能。
3. 检查在线服务的当前 API 条款、计费、内容再分发限制和隐私要求。
4. 不要把第三方服务返回的受版权保护内容、个人信息或 API 凭据打进发布包。
5. 如修改第三方文件，保留原始版权声明，并在发布说明中标注修改范围。

如第三方上游许可证与本文件记录不一致，应以上游仓库当前提供的许可证原文为准，并及时更新本文件。
