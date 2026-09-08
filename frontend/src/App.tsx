import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Archive,
  Bot,
  CheckCircle2,
  CircleDot,
  ChartNoAxesCombined,
  Copy,
  ChevronLeft,
  ChevronRight,
  Cpu,
  ExternalLink,
  FileText,
  FolderOpen,
  HeartHandshake,
  KeyRound,
  Loader2,
  MessageCircle,
  Power,
  Play,
  Plus,
  RefreshCcw,
  RotateCcw,
  Search,
  Save,
  Server,
  Sparkles,
  Square,
  TrendingUp,
  Video
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  fetchAgents,
  fetchAgentLogs,
  fetchWorkflow,
  fetchWorkflows,
  cancelWorkflow,
  analyzeStocks,
  fetchStockSourcesHealth,
  fetchMoneyPrinterTurboStatus,
  fetchStatus,
  fetchSystemStatus,
  restartBackend,
  runHotVideoWorkflow,
  runAgent,
  resumeWorkflow,
  stepWorkflow,
  runMoneyPrinterTurbo,
  scoutTopics,
  shutdownAll,
  startBackend,
  stopBackend,
  stopFrontend
  ,exportWorkflow
  ,importWorkflow
  ,fetchTimeoutSettings
  ,updateTimeoutSettings
  ,fetchOutputDirectorySettings
  ,updateOutputDirectorySettings
  ,selectDirectory
  ,openArtifactsFolder
  ,fetchEnvSettings
  ,updateEnvSettings
} from "./api";
const API_BASE = "";
import { navItems, pipeline, roleIcons } from "./data";
import type {
  Agent,
  AgentOutput,
  ApiStatus,
  MoneyPrinterTurboRunResult,
  MoneyPrinterTurboStatus,
  ManagedServiceStatus,
  SystemStatus,
  TopicSeed,
  WorkflowRun
  ,Topic
  ,StockAnalysisResult
  ,EngagementComment
  ,TimeoutSettings
  ,ViralAnalysisConfig
  ,OutputDirectorySettings
  ,EnvSettings
  ,AgentTaskLog
} from "./types";

type ViewId = (typeof navItems)[number]["id"];
type AgentTaskStatus = "idle" | "running" | "completed" | "failed";

const agentTaskStatusText: Record<AgentTaskStatus, string> = {
  idle: "待调用",
  running: "执行中",
  completed: "已完成",
  failed: "执行失败"
};

const defaultSeed: TopicSeed = {
  domain: "AI 圈",
  brief: "近期 AI 产品、模型、创业工具或内容生产热点",
  audience: "关注 AI 工具的一线创作者和创业者",
  duration_seconds: 110,
  video_aspect: "vertical"
};

const defaultTimeoutSettings: TimeoutSettings = {
  news_fetch_timeout_seconds: 90,
  model_timeout_seconds: 30,
  workflow_timeout_seconds: 300
};

const defaultViralAnalysis: ViralAnalysisConfig = {
  source: "socialdatax",
  enabled: true,
  manual_content: ""
};

const statusText = {
  live: "实时 AI",
  "local-template": "本地模板"
};

// 中文说明：函数「cn」负责完成该界面的状态处理、交互逻辑或数据转换。
function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/** Render model-produced Markdown consistently across every result surface. */
// 中文说明：函数「MarkdownContent」负责完成该界面的状态处理、交互逻辑或数据转换。
function MarkdownContent({ content, className }: { content: string; className?: string }) {
  return (
    <div className={cn("markdown-content", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ""}</ReactMarkdown>
    </div>
  );
}

// A stale browser snapshot can outlive the backend filter. Keep collection
// diagnostics out of the visible candidate cards until the server refreshes.
// 中文说明：函数「isDiagnosticTopic」负责完成该界面的状态处理、交互逻辑或数据转换。
function isDiagnosticTopic(topic: Topic): boolean {
  const text = `${topic.title} ${topic.source_hint} ${topic.angle}`.toLowerCase();
  return /(缺乏可用来源|不构成.{0,12}(热点|候选)|本批次|仅检测到|未出现|来源不足|模型未返回|报错|(?:执行|请求|抓取|来源|模型|搜索|接口).{0,8}(?:失败|错误|超时)|(?:失败|错误|超时).{0,8}(?:执行|请求|抓取|来源|模型|搜索|接口)|\b(error|failed|failure|exception|timeout)\b)/i.test(text);
}

function readSaved<T>(key: string, fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return value ? JSON.parse(value) as T : fallback;
  } catch {
    return fallback;
  }
}

// 中文说明：函数「readSavedRun」负责完成该界面的状态处理、交互逻辑或数据转换。
function readSavedRun(): WorkflowRun | null {
  const saved = readSaved<WorkflowRun | null>("signalforge.currentRun", null);
  if (!saved || saved.status !== "running") return saved;
  // A browser snapshot cannot prove that a server task is still alive.
  // Treat an old running snapshot as resumable until the server refresh wins.
  return {
    ...saved,
    status: "failed",
    error: saved.error || "页面恢复了一个未完成任务，请继续重试",
    resumable: true,
    completed_at: null
  };
}

// 中文说明：函数「readSavedView」负责完成该界面的状态处理、交互逻辑或数据转换。
function readSavedView(): ViewId {
  const saved = readSaved<string>("signalforge.activeView", "overview");
  return navItems.some((item) => item.id === saved) ? saved as ViewId : "overview";
}

// 中文说明：函数「readViralAnalysis」负责完成该界面的状态处理、交互逻辑或数据转换。
function readViralAnalysis(): ViralAnalysisConfig {
  const saved = readSaved<Partial<ViralAnalysisConfig>>("signalforge.viralAnalysis", {});
  return {
    ...defaultViralAnalysis,
    ...saved,
    enabled: saved.enabled !== false,
    manual_content: saved.manual_content ?? ""
  };
}

const viewMeta: Record<ViewId, { title: string; subtitle: string }> = {
  overview: {
    title: "热讯工坊调度台",
    subtitle: "从热点到可发布短视频的一人公司流水线"
  },
  radar: {
    title: "热点雷达",
    subtitle: "给热点监控员一个方向，快速形成可选题池。"
  },
  stocks: {
    title: "股票分析",
    subtitle: "财经、股票和股票新闻统一走 Stock Analysis Skill。"
  },
  editing: {
    title: "剪辑队列",
    subtitle: "查看视频剪辑员生成的画幅、配音、字幕、素材和导出方案。"
  },
  engagement: {
    title: "互动回复",
    subtitle: "把评论区、私信和内容反馈交给最合适的 AI 员工跟进"
  },
  settings: {
    title: "设置",
    subtitle: "检查模型、密钥变量、Base URL 和本地工作区约定。"
  },
  agent_hotspot_monitor: { title: "热点监控员", subtitle: "独立搜集、排序并核验热点候选。" },
  agent_viral_analyst: { title: "爆款分析师", subtitle: "独立分析爆款内容规律，拆解传播钩子、情绪冲突和受众动机。" },
  agent_copywriter: { title: "文案助手", subtitle: "独立生成短视频口播脚本。" },
  agent_video_editor: { title: "视频剪辑员", subtitle: "独立生成剪辑、字幕和配音方案。" },
  agent_operator: { title: "运营大师", subtitle: "独立生成发布、互动和复盘方案。" },
  agent_product_manager: { title: "产品经理", subtitle: "独立完成需求拆解、调研和产品建议。" },
  agent_programmer: { title: "程序员", subtitle: "独立完成自动化、接口和工程任务建议。" },
  agent_stock_assistant: { title: "股票助手", subtitle: "独立处理股票和财经信息分析。" },
  agent_healer: { title: "心理疗愈师", subtitle: "独立提供情绪支持和安全边界提示。" }
};

const employeeIds = [
  "hotspot_monitor",
  "viral_analyst",
  "copywriter",
  "video_editor",
  "operator",
  "product_manager",
  "programmer",
  "stock_assistant",
  "healer"
] as const;

// 中文说明：函数「employeeIdFromView」负责完成该界面的状态处理、交互逻辑或数据转换。
function employeeIdFromView(view: ViewId): string | null {
  return view.startsWith("agent_") ? view.slice("agent_".length) : null;
}

// 中文说明：函数「formatWorkflowError」负责完成该界面的状态处理、交互逻辑或数据转换。
function formatWorkflowError(run: WorkflowRun, fallback = "") {
  let detail = run.error || fallback;
  if (run.current_stage) {
    const rawPrefix = `${run.current_stage}:`;
    if (detail.startsWith(rawPrefix)) {
      detail = `阶段：${run.current_stage}。\n${detail.slice(rawPrefix.length).trim()}`;
    } else if (!detail.startsWith(`阶段：${run.current_stage}`)) {
      detail = `阶段：${run.current_stage}。\n${detail}`;
    }
  }
  return detail.replace(/来源状态：\s*/, "来源状态：\n").replace(/;\s+/g, "\n");
}

// 中文说明：函数「ShellNav」负责完成该界面的状态处理、交互逻辑或数据转换。
function ShellNav({
  activeView,
  onViewChange,
  closing,
  shutdownComplete,
  onShutdown
}: {
  activeView: ViewId;
  onViewChange: (view: ViewId) => void;
  closing: boolean;
  shutdownComplete: boolean;
  onShutdown: () => void;
}) {
  const moreViewIds = new Set([
    "agent_product_manager",
    "agent_programmer",
    "agent_stock_assistant",
    "agent_healer",
    "radar",
    "stocks",
    "editing",
    "engagement"
  ]);
  const primaryItems = navItems.filter((item) => item.id !== "settings" && !moreViewIds.has(item.id));
  const moreItems = navItems.filter((item) => moreViewIds.has(item.id));
  const [moreOpen, setMoreOpen] = useState(() => moreViewIds.has(activeView));

  useEffect(() => {
    if (moreViewIds.has(activeView)) setMoreOpen(true);
  }, [activeView]);

  // 中文说明：函数「renderNavItem」负责完成该界面的状态处理、交互逻辑或数据转换。
  const renderNavItem = (item: (typeof navItems)[number], subItem = false) => {
    const Icon = item.icon;
    return (
      <button
        className={cn("nav-item", subItem && "nav-sub-item", activeView === item.id && "active")}
        onClick={() => onViewChange(item.id)}
        type="button"
        aria-current={activeView === item.id ? "page" : undefined}
        key={item.id}
      >
        <Icon size={subItem ? 17 : 18} />
        <span>{item.label}</span>
      </button>
    );
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">热</div>
        <div>
          <strong>热讯工坊</strong>
          <span>AI 一人公司</span>
        </div>
      </div>
      {/* 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。

      <div className="nav-scroll-area">
        <nav className="nav-list" aria-label="主导航">
          {primaryItems.filter((item) => item.id === "overview").map((item) => renderNavItem(item))}
          <div className="nav-section-label">独立工作台</div>
          {primaryItems.filter((item) => item.id !== "overview").map((item) => renderNavItem(item))}
        </nav>
        <div className="nav-more-group">
          <details
            className="nav-collapsible"
            open={moreOpen}
            onToggle={(event) => setMoreOpen(event.currentTarget.open)}
          >
            <summary className="nav-collapse-summary">
              <span>更多</span>
              <ChevronRight size={15} aria-hidden="true" />
            </summary>
            <div className="nav-collapsible-items">
              {moreItems.map((item) => renderNavItem(item, true))}
            </div>
          </details>
        </div>
      </div>

      <div className="sidebar-settings">
        <div className="nav-divider" aria-hidden="true" />
        {renderNavItem(navItems.find((item) => item.id === "settings")!)}
      </div>

      <div className="boss-card">
        <span>实时 AI 工作台</span>
        <strong>你负责方向与验收</strong>
        <p>Agent 实时调用模型，协同完成收集、分析、写作、剪辑和运营。</p>
      </div>

      <button className="shutdown-button" onClick={onShutdown} disabled={closing || shutdownComplete} type="button">
        {closing ? <Loader2 className="spin" size={17} /> : <Power size={17} />}
        <span>{closing ? "正在关闭" : shutdownComplete ? "服务已关闭" : "退出并关闭服务"}</span>
      </button>
    </aside>
  );
}

// 中文说明：函数「TopBar」负责完成该界面的状态处理、交互逻辑或数据转换。
function TopBar({
  activeView,
  status,
  running,
  onRun
}: {
  activeView: ViewId;
  status: ApiStatus | null;
  running: boolean;
  onRun: () => void;
}) {
  const meta = viewMeta[activeView];
  const isEmployeeView = activeView.startsWith("agent_");
  const isConsoleView = activeView === "overview";

  return (
    <header className="topbar">
      <div>
        <h1>{isEmployeeView ? "独立工作台" : meta.title}</h1>
        {!isEmployeeView && <p>{meta.subtitle}</p>}
      </div>
        <div className="topbar-actions">
          <div className={cn("api-pill", status?.mode === "live" ? "ok" : "warn")} title={status?.diagnostic ?? undefined}>
            {status?.mode === "live" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{status ? statusText[status.mode] : "检测中"}</span>
          </div>
          {isConsoleView && (
            <button className="primary-button" onClick={onRun} disabled={running}>
              {running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
              <span>{running ? "运行中" : "运行工作流"}</span>
            </button>
          )}
        </div>
    </header>
  );
}

// 中文说明：函数「PipelineBoard」负责完成该界面的状态处理、交互逻辑或数据转换。
function PipelineBoard({ run, running, onNew, onStep, onCancel, onRerun, onOpenArtifacts }: { run: WorkflowRun | null; running: boolean; onNew: () => void; onStep: () => void; onCancel: () => void; onRerun: (stage: string) => void; onOpenArtifacts: () => void }) {
  const completedIds = new Set(run?.outputs.map((output) => output.agent_id) ?? []);
  const stageStatus = run?.stage_status ?? {};
  const statusLabels = { pending: "待调度", running: "执行中", completed: "已产出", failed: "失败" };

  return (
    <section className="panel pipeline-panel">
      <div className="panel-heading">
        <div>
          <h2>内容生产流水线</h2>
          <p>热点监控员选题 -&gt; 爆款分析师定结构 -&gt; 文案助手写脚本 -&gt; 剪辑员成片。</p>
        </div>
          <div className="pipeline-actions">
            <span className={cn("run-state", (running || run?.status === "running" || run?.status === "queued") && "running", run?.status === "completed" && "done", run?.status === "failed" && "failed")}>
              {running ? "执行中" : run?.status === "paused" ? "已暂停" : run?.status === "queued" ? "待调度" : run?.status === "failed" ? "执行失败" : run?.status === "completed" ? "已完成" : "待开始"}
            </span>
            <button className="ghost-button compact" onClick={onNew} disabled={running} type="button">
              <Plus size={15} />
              <span>新任务</span>
            </button>
            <button className="ghost-button compact" onClick={onOpenArtifacts} type="button" title="打开全部产物文件夹">
              <FolderOpen size={15} />
              <span>打开产物文件夹</span>
            </button>
            {run && run.status !== "completed" && <button className="ghost-button compact" onClick={onStep} disabled={running} type="button">执行下一步</button>}
            {running && <button className="danger-button compact" onClick={onCancel} type="button"><Square size={15} /><span>停止任务</span></button>}
          </div>
      </div>
      {run?.logs?.length ? (
        <details className="run-logs">
          <summary>查看执行日志（{run.logs.length} 条）</summary>
          <div className="run-log-list">
            {run.logs.slice().reverse().map((entry, index) => (
              <div className={cn("run-log-entry", entry.level === "error" && "error")} key={`${entry.timestamp}-${index}`}>
                <time>{new Date(entry.timestamp).toLocaleTimeString()}</time>
                <span>{entry.stage ? `[${entry.stage}] ` : ""}{entry.message}</span>
                {entry.detail && <code>{entry.detail}</code>}
              </div>
            ))}
          </div>
          {run.log_file && <small className="log-path">日志文件：{run.log_file}</small>}
        </details>
      ) : null}
      {/* 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。

      <div className="pipeline-grid">
        {pipeline.map((stage, index) => {
          const Icon = roleIcons[stage.agentId] ?? Bot;
          const state = stageStatus[stage.agentId] ?? (completedIds.has(stage.agentId) ? "completed" : "pending");
          const done = state === "completed";
          const active = state === "running" || (running && index === 0 && !run);
          return (
            <article className={cn("stage-card", done && "done", active && "active", state === "failed" && "failed")} key={stage.agentId}>
              <div className="stage-head">
                <div className="stage-icon">
                  <Icon size={18} />
                </div>
                {run && !running && state !== "running" && <button className="ghost-button rerun-stage" type="button" onClick={() => onRerun(stage.agentId)}>重跑</button>}
              </div>
              <h3>{stage.title}</h3>
              <strong>{stage.action}</strong>
              <p>{stage.description}</p>
              <div className="stage-foot">
                {done ? <CheckCircle2 size={16} /> : <CircleDot size={16} />}
                <span>{statusLabels[state as keyof typeof statusLabels] ?? "待调度"}</span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

// 中文说明：函数「SeedPanel」负责完成该界面的状态处理、交互逻辑或数据转换。
function SeedPanel({
  seed,
  onChange
}: {
  seed: TopicSeed;
  onChange: (seed: TopicSeed) => void;
}) {
  return (
    <section className="panel seed-panel">
      <div className="panel-heading tight">
        <div>
          <h2>老板指令</h2>
          <p>给整条流水线的本轮方向；各员工的专属设置请在左侧员工页维护。</p>
        </div>
      </div>
      <label>
        <span>领域</span>
        <input value={seed.domain} onChange={(event) => onChange({ ...seed, domain: event.target.value })} />
      </label>
      <label>
        <span>选题方向</span>
        <textarea value={seed.brief} onChange={(event) => onChange({ ...seed, brief: event.target.value })} />
      </label>
      <label>
        <span>目标受众</span>
        <input value={seed.audience} onChange={(event) => onChange({ ...seed, audience: event.target.value })} />
      </label>
      <label>
        <span>脚本秒数</span>
        <input
          type="number"
          min={30}
          max={240}
          value={seed.duration_seconds}
          onChange={(event) => onChange({ ...seed, duration_seconds: Number(event.target.value) })}
        />
      </label>
      <label>
        <span>视频画幅</span>
        <select
          value={seed.video_aspect}
          onChange={(event) => onChange({ ...seed, video_aspect: event.target.value as TopicSeed["video_aspect"] })}
        >
          <option value="vertical">竖版 1080 x 1920（9:16）</option>
          <option value="horizontal">横版 1920 x 1080（16:9）</option>
        </select>
      </label>
      <div className="settings-handoff">
        <ChartNoAxesCombined size={16} />
        <span>总控制台的爆款分析设置请前往“设置”页；<br />左侧员工页只影响对应独立工作台。</span>
      </div>
    </section>
  );
}

// 中文说明：函数「AgentRoster」负责完成该界面的状态处理、交互逻辑或数据转换。
function AgentRoster({ agents }: { agents: Agent[] }) {
  const pipelineIds = new Set(pipeline.map((stage) => stage.agentId));
  const groups = [
    { title: "流水线员工", hint: "参与热点到成片的固定流程", items: agents.filter((agent) => pipelineIds.has(agent.id)) },
    { title: "其他员工", hint: "按需独立调用，不自动加入流水线", items: agents.filter((agent) => !pipelineIds.has(agent.id)) }
  ];
  return (
    <section className="panel roster-panel">
      <div className="panel-heading tight">
        <div>
          <h2>AI 员工分工</h2>
          <p>流水线员工按阶段协作；其他员工只在需要时独立调用。</p>
        </div>
      </div>
      {groups.map((group) => <div className="roster-group" key={group.title}>
        <div className="roster-group-heading"><strong>{group.title}</strong><span>{group.hint}</span></div>
      <div className="roster-list">
        {group.items.map((agent) => {
          const Icon = roleIcons[agent.id] ?? Bot;
          return (
            <article className="agent-row" key={agent.id}>
              <div className="agent-icon">
                <Icon size={18} />
              </div>
              <div className="agent-main">
                <div>
                  <strong>{agent.title}</strong>
                </div>
                <p>{agent.focus}</p>
              </div>
              <span className={cn("agent-dot", `status-${agent.status}`)} aria-label={agent.status} />
            </article>
          );
        })}
      </div></div>)}
    </section>
  );
}

// 中文说明：函数「TopicList」负责完成该界面的状态处理、交互逻辑或数据转换。
function TopicList({ run, topics, selectable, selectedTitle, onSelect }: { run?: WorkflowRun | null; topics?: Topic[]; selectable?: boolean; selectedTitle?: string | null; onSelect?: (title: string | null) => void }) {
  // 中文说明：函数「items」负责完成该界面的状态处理、交互逻辑或数据转换。
  const items = (topics ?? run?.topics ?? []).filter((topic) => !isDiagnosticTopic(topic));
  return (
    <section className="panel topics-panel">
      <div className="panel-heading tight">
        <div>
          <h2>热点候选</h2>
          <p>由热点监控员初筛，爆款分析师负责判断传播结构。不勾选则默认第一个。</p>
        </div>
      </div>
      <div className="topic-list">
        {items.map((topic) => (
            <article className={cn("topic-card", selectable && "topic-selectable", selectedTitle === topic.title && "topic-selected")} key={topic.title}>
              {selectable && <label className="topic-check" onClick={(event) => event.stopPropagation()}><input type="checkbox" checked={selectedTitle === topic.title} onChange={() => onSelect?.(selectedTitle === topic.title ? null : topic.title)} aria-label={`选择热点：${topic.title}`} /></label>}
            <div className="heat">
              <Sparkles size={15} />
              <span>{topic.heat}</span>
            </div>
            <h3>{topic.title}</h3>
            <p>{topic.angle}</p>
            <small>{topic.source_hint}</small>
            <small className={cn("verification-badge", topic.verification_status === "verified" && "verified")}>
              {topic.verification_status === "verified" ? "已通过独立来源核验" : "待完成独立来源核验"}
            </small>
          </article>
        ))}
        {!items.length && (
          <div className="empty-state">
            <RefreshCcw size={20} />
            <span>运行工作流后，这里会显示热点候选。</span>
          </div>
        )}
      </div>
    </section>
  );
}

// 中文说明：函数「OutputList」负责完成该界面的状态处理、交互逻辑或数据转换。
function OutputList({ outputs }: { outputs: AgentOutput[] }) {
  // 中文说明：函数「agentTitle」负责完成该界面的状态处理、交互逻辑或数据转换。
  const agentTitle = (agentId: string) => {
    const pipelineStage = pipeline.find((stage) => stage.agentId === agentId);
    if (pipelineStage) return pipelineStage.title;
    return navItems.find((item) => item.id === `agent_${agentId}`)?.label ?? agentId;
  };

  return (
    <section className="panel outputs-panel">
      <div className="panel-heading tight">
        <div>
          <h2>产物与日志</h2>
          <p>每个 Agent 的结果都会保存到本地任务记录。</p>
        </div>
      </div>
      <div className="outputs-list">
        {outputs.map((output) => (
          <details className="output-item" key={`${output.agent_id}-${output.created_at}`}>
            <summary>
              <span>{agentTitle(output.agent_id)}</span>
              <small>{output.artifact_path}</small>
              <ChevronRight className="output-item-chevron" size={16} aria-hidden="true" />
            </summary>
            <MarkdownContent content={output.content} />
            {output.agent_id === "operator" && (() => {
              const match = output.content.match(/封面文件：([^\n]+)/);
              const coverPath = match?.[1]?.trim();
              return coverPath ? <img className="operator-cover-preview" src={`${API_BASE}/api/artifacts/preview?path=${encodeURIComponent(coverPath)}`} alt="运营大师生成的封面" /> : null;
            })()}
          </details>
        ))}
        {!outputs.length && (
          <div className="empty-state">
            <Copy size={20} />
            <span>暂无产物。先运行一次完整工作流。</span>
          </div>
        )}
      </div>
    </section>
  );
}

// 中文说明：函数「SettingsStrip」负责完成该界面的状态处理、交互逻辑或数据转换。
function SettingsStrip({ status, collapsed, onToggle }: { status: ApiStatus | null; collapsed: boolean; onToggle: () => void }) {
  return (
    <section className={cn("settings-strip", collapsed && "collapsed")} aria-label="AI 运行状态">
      {!collapsed && <div className="settings-strip-content">
        <div><span>Key Path</span><strong>{status?.key_preview ?? "未配置"}</strong></div>
        <div><span>Base URL</span><strong>{status?.base_url ?? "https://api.openlux.ai/v1"}</strong></div>
        <div><span>Model</span><strong>{status?.model ?? "中转站自动选择"}</strong></div>
        <div><span>AI Health</span><strong>{status?.model_available ? "模型可用" : status?.diagnostic ?? "检查中"}</strong></div>
      </div>}
      <button className="settings-strip-toggle" type="button" onClick={onToggle} aria-label={collapsed ? "展开 AI 运行状态" : "收起 AI 运行状态"} title={collapsed ? "展开 AI 运行状态" : "收起 AI 运行状态"}>
        {collapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </button>
    </section>
  );
}

// 中文说明：函数「RadarView」负责完成该界面的状态处理、交互逻辑或数据转换。
function RadarView({ topics, seed, onChange, onRun, running }: {
  topics: Topic[];
  seed: TopicSeed;
  onChange: (seed: TopicSeed) => void;
  onRun: () => void;
  running: boolean;
}) {
  return (
    <div className="single-view">
      <section className="panel action-panel">
        <div className="panel-heading">
          <div>
            <h2>热点监控员的热点雷达</h2>
            <p>输入领域和方向后，热点监控员会给出候选选题、热度、线索和风险。</p>
          </div>
          <button className="primary-button" onClick={onRun} disabled={running} type="button">
            {running ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
            <span>{running ? "扫描中" : "扫描热点"}</span>
          </button>
        </div>
        <div className="form-grid">
          <label>
            <span>领域</span>
            <input value={seed.domain} onChange={(event) => onChange({ ...seed, domain: event.target.value })} />
          </label>
          <label>
            <span>目标受众</span>
            <input value={seed.audience} onChange={(event) => onChange({ ...seed, audience: event.target.value })} />
          </label>
          <label className="wide">
            <span>选题方向</span>
            <textarea value={seed.brief} onChange={(event) => onChange({ ...seed, brief: event.target.value })} />
          </label>
        </div>
      </section>
      <TopicList topics={topics} />
    </div>
  );
}

// 中文说明：函数「EditingQueueView」负责完成该界面的状态处理、交互逻辑或数据转换。
function EditingQueueView({ outputs, seed }: { outputs: AgentOutput[]; seed: TopicSeed }) {
  const editingOutputs = outputs.filter((output) => ["video_editor", "operator"].includes(output.agent_id));
  const [mptStatus, setMptStatus] = useState<MoneyPrinterTurboStatus | null>(null);
  const [mptRunning, setMptRunning] = useState(false);
  const [mptResult, setMptResult] = useState<MoneyPrinterTurboRunResult | null>(null);

  useEffect(() => {
    fetchMoneyPrinterTurboStatus()
      .then(setMptStatus)
      .catch(() => setMptStatus(null));
  }, []);

  const script = outputs.find((output) => output.agent_id === "copywriter");
  const subject = script?.content ?? seed.brief;

  async function handleMptRun() {
    setMptRunning(true);
    setMptResult(null);
    try {
      const result = await runMoneyPrinterTurbo(subject);
      setMptResult(result);
    } finally {
      setMptRunning(false);
    }
  }

  const missingEnv = mptStatus?.missing_env ?? [];
  const hasLlmKey = !missingEnv.includes("AI_API_KEY");
  const hasPexelsKey = !missingEnv.includes("MPT_PEXELS_API_KEY");

  return (
    <div className="single-view">
      <section className="panel mpt-panel">
        <div className="panel-heading tight">
          <div>
            <h2>MoneyPrinterTurbo</h2>
            <p>视频剪辑员的专属剪辑能力，基于 MoneyPrinterTurbo。</p>
          </div>
          <span className={cn("run-state", mptStatus?.installed && "done")}>
            {mptStatus?.installed ? "installed" : "checking"}
          </span>
        </div>
        <div className="mpt-grid">
          <div>
            <span>来源</span>
            <strong>
              <a href="https://github.com/harry0703/MoneyPrinterTurbo" target="_blank" rel="noreferrer">
                MoneyPrinterTurbo 官方仓库
                <ExternalLink size={13} aria-hidden="true" />
              </a>
            </strong>
          </div>
        </div>
        {!!missingEnv.length && (
          <div className="missing-env">
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。
            {/* 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
            <AlertCircle size={16} />
            <div>
              <strong>真实成片需要配置以下服务：</strong>
              <span className={cn(hasLlmKey && "config-ready")}>AI 密钥：{hasLlmKey ? "已配置" : "请配置 AI_API_KEY"}</span>
              <span className={cn(hasPexelsKey && "config-ready")}>视频素材：{hasPexelsKey ? "已配置" : "请配置 MPT_PEXELS_API_KEY（"}<a href="https://www.pexels.com/api/" target="_blank" rel="noreferrer">前往 Pexels API 获取</a>{!hasPexelsKey && "）"}</span>
            </div>
          </div>
        )}
        <div className="project-file-actions">
          <button className="primary-button" onClick={handleMptRun} disabled={mptRunning || !mptStatus?.installed} type="button">
            {mptRunning ? <Loader2 className="spin" size={18} /> : <Video size={18} />}
            <span>{mptRunning ? "成片中" : "用 MoneyPrinterTurbo 成片"}</span>
          </button>
          {mptResult && (
            <div className={cn("mpt-result", mptResult.status === "completed" && "done", ["failed", "missing_skill", "timeout"].includes(mptResult.status) && "failed")}>
              <strong>{mptResult.status}</strong>
              <span>
                {mptResult.video_files.length
                  ? mptResult.video_files.join("、")
                  : mptResult.stdout.split("\n").find((line) => line.includes("MPT_NEEDS_INPUT")) ?? mptResult.stderr}
              </span>
            </div>
          )}
        </div>
      </section>
      <section className="panel queue-panel">
        <div className="panel-heading tight">
          <div>
            <h2>剪辑与发布队列</h2>
            <p>视频剪辑员负责剪辑计划，运营大师负责发布策略；完整跑一次工作流后会出现队列。</p>
          </div>
        </div>
        <div className="queue-grid">
          {editingOutputs.map((output) => (
            <article className="queue-card" key={`${output.agent_id}-${output.created_at}`}>
              <div className="queue-icon">{output.agent_id === "video_editor" ? <Video size={18} /> : <Archive size={18} />}</div>
              <div>
                <span>{pipeline.find((stage) => stage.agentId === output.agent_id)?.title ?? navItems.find((item) => item.id === `agent_${output.agent_id}`)?.label ?? output.agent_id}</span>
                <h3>{output.title}</h3>
                <MarkdownContent content={output.content} className="queue-card-markdown" />
                <small>{output.artifact_path}</small>
              </div>
            </article>
          ))}
          {!editingOutputs.length && (
            <div className="empty-state">
              <Video size={20} />
              <span>运行完整工作流后，这里会显示剪辑与发布方案。</span>
            </div>
          )}
        </div>
      </section>
      <OutputList outputs={editingOutputs} />
    </div>
  );
}

// 中文说明：函数「AgentsView」负责完成该界面的状态处理、交互逻辑或数据转换。
function AgentsView({ agents }: { agents: Agent[] }) {
  return (
    <section className="panel agent-detail-panel">
      <div className="panel-heading tight">
        <div>
          <h2>员工档案</h2>
          <p>每个 AI 员工都有清晰职责和技能来源。</p>
        </div>
      </div>
      <div className="agent-detail-grid">
        {agents.map((agent) => {
          const Icon = roleIcons[agent.id] ?? Bot;
          return (
            <article className="agent-detail-card" key={agent.id}>
              <div className="stage-head">
                <div className="stage-icon">
                  <Icon size={18} />
                </div>
                <span>{agent.title}</span>
              </div>
              <h3>{agent.title}</h3>
              <p>{agent.role}</p>
              <div className="skill-list">
                {agent.skills.length ? (
                  agent.skills.map((skill) => (
                    <div className="skill-item" key={skill.name}>
                      <strong>{skill.name}</strong>
                      <span>{skill.description}</span>
                      <small>{skill.source}</small>
                    </div>
                  ))
                ) : (
                  <span className="skill-empty">未安装专项 Skill</span>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

// 中文说明：函数「EmployeeWorkbench」负责完成该界面的状态处理、交互逻辑或数据转换。
function EmployeeWorkbench({
  agent,
  seed: initialSeed,
  viralAnalysis: initialViralAnalysis,
  onRun,
  busy,
  taskStatus,
  error,
  output,
  logs
}: {
  agent: Agent;
  seed: TopicSeed;
  viralAnalysis: ViralAnalysisConfig;
  onRun: (prompt: string, settings: Record<string, unknown>) => void;
  busy: boolean;
  taskStatus: AgentTaskStatus;
  error: string | null;
  output: AgentOutput | null;
  logs: AgentTaskLog[];
}) {
  const [seed, setSeed] = useState<TopicSeed>(() => ({
    ...initialSeed,
    ...readSaved<Partial<TopicSeed>>(`signalforge.employee.${agent.id}.seed`, {})
  }));
  const [viralAnalysis, setViralAnalysis] = useState<ViralAnalysisConfig>(() => readSaved(`signalforge.employee.${agent.id}.viral`, initialViralAnalysis));
  const [prompt, setPrompt] = useState("");
  const [videoFormat, setVideoFormat] = useState("vertical");
  const [editingRequirements, setEditingRequirements] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);
  const Icon = roleIcons[agent.id] ?? Bot;
  const employeeMeta = viewMeta[`agent_${agent.id}` as ViewId];
  const isViral = agent.id === "viral_analyst";
  const isWriter = agent.id === "copywriter";
  const isHotspot = agent.id === "hotspot_monitor";

  useEffect(() => { window.localStorage.setItem(`signalforge.employee.${agent.id}.seed`, JSON.stringify(seed)); }, [agent.id, seed]);
  useEffect(() => { window.localStorage.setItem(`signalforge.employee.${agent.id}.viral`, JSON.stringify(viralAnalysis)); }, [agent.id, viralAnalysis]);
  useEffect(() => {
    const saved = readSaved<{ prompt?: string; videoFormat?: string; editingRequirements?: string; outputDir?: string; timeoutSeconds?: number }>(`signalforge.employee.${agent.id}.form`, {});
    setPrompt(saved.prompt ?? ""); setVideoFormat(saved.videoFormat ?? "vertical");
    setEditingRequirements(saved.editingRequirements ?? ""); setOutputDir(saved.outputDir ?? "");
    setTimeoutSeconds(Number.isFinite(saved.timeoutSeconds) && (saved.timeoutSeconds ?? 0) >= 0 ? Math.min(86400, Math.floor(saved.timeoutSeconds!)) : 300);
  }, [agent.id]);
  useEffect(() => { window.localStorage.setItem(`signalforge.employee.${agent.id}.form`, JSON.stringify({ prompt, videoFormat, editingRequirements, outputDir, timeoutSeconds })); }, [agent.id, prompt, videoFormat, editingRequirements, outputDir, timeoutSeconds]);

  // 中文说明：函数「submit」负责完成该界面的状态处理、交互逻辑或数据转换。
  function submit() {
    onRun(prompt, {
      domain: seed.domain,
      audience: seed.audience,
      duration_seconds: seed.duration_seconds,
      topic: seed.brief,
      angle: seed.domain,
      source: viralAnalysis.source
      ,manual_content: viralAnalysis.manual_content
      ,stocks: seed.brief
      ,format: agent.id === "video_editor" ? videoFormat : undefined
      ,editing_requirements: agent.id === "video_editor" ? editingRequirements : undefined
      ,script: agent.id === "video_editor" ? prompt : undefined
      ,output_dir: agent.id === "video_editor" ? outputDir : undefined
      ,artifact_output_dir: agent.id === "operator" ? outputDir : undefined
      ,timeout_seconds: timeoutSeconds
    });
  }

  return (
    <div className={cn("employee-workbench", isViral && "viral-workbench")}>
      <section className="panel employee-hero">
        <div className="stage-head">
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。
          {/* 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
          <div className="stage-icon"><Icon size={20} /></div>
        </div>
        <div className="employee-hero-copy">
          <h2>{agent.title}</h2>
          <p>{employeeMeta?.subtitle ?? agent.role}</p>
        </div>
        <div className="employee-task-summary" aria-live="polite">
          <span>独立任务</span>
          <strong className={cn("employee-task-state", taskStatus)}>{agentTaskStatusText[taskStatus]}</strong>
        </div>
      </section>
      <div className="employee-work-grid">
        <section className="panel employee-settings">
          <div className="panel-heading tight"><div><h2>调用设置</h2><p>只调用当前员工，不启动整条流水线。</p></div></div>
          {isHotspot && <>
            <label><span>领域</span><input value={seed.domain} onChange={(event) => setSeed({ ...seed, domain: event.target.value })} /></label>
            <label><span>受众</span><input value={seed.audience} onChange={(event) => setSeed({ ...seed, audience: event.target.value })} /></label>
          </>}
          {isWriter && <>
            <label><span>主题</span><textarea value={seed.brief} onChange={(event) => setSeed({ ...seed, brief: event.target.value })} /></label>
            <label><span>时长（秒）</span><input type="number" min={30} max={240} value={seed.duration_seconds} onChange={(event) => setSeed({ ...seed, duration_seconds: Number(event.target.value) })} /></label>
          </>}
          {agent.id === "video_editor" && <>
            <label><span>视频画幅</span><select className="workbench-select" value={videoFormat} onChange={(event) => setVideoFormat(event.target.value)}><option value="vertical">竖版 1080×1920</option><option value="horizontal">横版 1920×1080</option></select></label>
            <label><span>剪辑要求</span><textarea value={editingRequirements} onChange={(event) => setEditingRequirements(event.target.value)} placeholder="例如：突出开场钩子，字幕每 12-16 字断行" /></label>
            <label><span>视频输出目录</span><input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} placeholder="留空使用系统设置；例如 D:\\Videos\\SignalForge" /></label>
          </>}
          {agent.id === "operator" && <>
            <label><span>发布平台</span><select className="workbench-select" defaultValue="douyin"><option value="douyin">抖音</option><option value="xiaohongshu">小红书</option><option value="bilibili">B 站</option><option value="wechat">视频号</option></select></label>
            <label><span>运营目标</span><input defaultValue="提升完播率、收藏率和评论质量" /></label>
            <label><span>产物输出目录</span><input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} placeholder="留空使用系统设置；例如 D:\\Content\\运营方案" /></label>
          </>}
          {agent.id === "product_manager" && <label><span>分析类型</span><select className="workbench-select" defaultValue="需求拆解"><option>需求拆解</option><option>竞品分析</option><option>产品路线图</option></select></label>}
          {agent.id === "programmer" && <label><span>技术栈 / 输出形式</span><input defaultValue="Python、FastAPI、React；输出实施方案" /></label>}
          <label>
            <span>独立工作台超时（秒）</span>
            <div className="timeout-input-row">
              <input type="number" min={0} max={86400} value={timeoutSeconds === 0 ? "" : timeoutSeconds} onChange={(event) => setTimeoutSeconds(Math.max(0, Math.min(86400, Math.floor(Number(event.target.value) || 0))))} disabled={timeoutSeconds === 0} />
              <span className="timeout-toggle"><input type="checkbox" checked={timeoutSeconds === 0} onChange={(event) => setTimeoutSeconds(event.target.checked ? 0 : 300)} /><span>不限时</span></span>
            </div>
            <small className="field-hint">只影响当前员工独立调用，不会改变总控制台工作流超时。</small>
          </label>
          {isViral && <>
            <label className="switch-line switch-control">
              <input type="checkbox" checked={viralAnalysis.enabled} onChange={(event) => setViralAnalysis({ ...viralAnalysis, enabled: event.target.checked })} />
              <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
              <span className="switch-copy"><strong>{viralAnalysis.enabled ? "已启用爆款分析师" : "已关闭爆款分析师"}</strong><small>{viralAnalysis.enabled ? "流水线会执行这一阶段" : "流水线会跳过这一阶段"}</small></span>
            </label>
            <div className="segmented-control"><button className={cn("segment-button", viralAnalysis.source === "socialdatax" && "selected")} onClick={() => setViralAnalysis({ ...viralAnalysis, source: "socialdatax" })} type="button">SocialDataX</button><button className={cn("segment-button", viralAnalysis.source === "manual" && "selected")} onClick={() => setViralAnalysis({ ...viralAnalysis, source: "manual" })} type="button">手写分析</button></div>
            <small className="field-hint">仅影响当前员工独立工作台，不会改变总控制台任务。</small>
            {viralAnalysis.source === "manual" && <label><span>手写分析依据</span><textarea className="manual-analysis-input" value={viralAnalysis.manual_content} onChange={(event) => setViralAnalysis({ ...viralAnalysis, manual_content: event.target.value })} placeholder="填写具体爆款样本、数据或你的分析结论；不要粘贴角色提示词" /></label>}
          </>}
          {agent.id === "stock_assistant" && <label><span>股票代码或名称</span><input value={seed.brief} onChange={(event) => setSeed({ ...seed, brief: event.target.value })} placeholder="600519, TSLA" /></label>}
          <label><span>{agent.id === "video_editor" ? "脚本 / 口播文案" : "本次任务"}</span><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={isHotspot ? "例如：找今天影响普通创作者的 AI 行业热点" : agent.id === "video_editor" ? "粘贴完整脚本；剪辑员会按脚本生成时间轴、镜头、字幕和导出方案" : "描述这次要让员工完成什么"} /></label>
          <button className="primary-button" type="button" onClick={submit} disabled={busy}>{busy ? <Loader2 className="spin" size={17} /> : <Play size={17} />}<span>{busy ? "执行中" : `调用${agent.title}`}</span></button>
          {error && <div className="employee-task-error"><AlertCircle size={16} /><span>{error}</span></div>}
        </section>
        <div className="employee-results-column">
          <section className="panel employee-output">
            <div className="panel-heading tight"><div><h2>独立产物</h2><p>结果会保存到本次独立调用记录。</p></div></div>
            {output ? <><small>{output.artifact_path}</small><MarkdownContent content={output.content} /></> : <div className="empty-state employee-output-empty"><Copy size={20} /><span>还没有调用结果。</span></div>}
          </section>
          <section className="panel employee-log-panel">
            <div className="panel-heading tight"><div><h2>本员工日志</h2></div></div>
            {logs.length ? <div className="employee-log-list">{logs.slice().reverse().map((entry, index) => <div className="run-log-entry" key={`${entry.timestamp}-${index}`}><time>{new Date(entry.timestamp).toLocaleTimeString()}</time><span>{entry.message}</span></div>)}</div> : <small>暂无独立任务日志。</small>}
          </section>
        </div>
      </div>
    </div>
  );
}

const initialComments: EngagementComment[] = [
  { id: "c-101", author: "小树洞", content: "最近总是很焦虑，明明没有发生什么，却每天都觉得好累。该怎么办？", source: "视频评论区 · 《成年人如何面对焦虑》", time: "刚刚", category: "情绪支持", assignedAgentId: "healer", priority: "高", status: "待回复" },
  { id: "c-102", author: "Momo", content: "这个工作流可以接入小红书的评论吗？想用在自己的账号上。", source: "视频评论区 · 《AI 员工工作流》", time: "8 分钟前", category: "产品咨询", assignedAgentId: "operator", priority: "普通", status: "待回复" },
  { id: "c-103", author: "阿远", content: "如果想系统学习这套方法，建议先从哪个岗位开始？", source: "私信", time: "21 分钟前", category: "内容讨论", assignedAgentId: "product_manager", priority: "普通", status: "待回复" },
  { id: "c-104", author: "晚风", content: "看完视频感觉被理解了，谢谢你们认真做这样的内容。", source: "视频评论区 · 《给低能量的你》", time: "36 分钟前", category: "情绪支持", assignedAgentId: "healer", priority: "普通", status: "待回复" }
];

// 中文说明：函数「EngagementView」负责完成该界面的状态处理、交互逻辑或数据转换。
function EngagementView({ agents }: { agents: Agent[] }) {
  const [comments, setComments] = useState(initialComments);
  const [selectedId, setSelectedId] = useState(initialComments[0].id);
  const [draft, setDraft] = useState("");
  const selected = comments.find((comment) => comment.id === selectedId) ?? comments[0];
  // 中文说明：函数「agentName」负责完成该界面的状态处理、交互逻辑或数据转换。
  const agentName = (id: string) => agents.find((agent) => agent.id === id)?.title ?? id;

  useEffect(() => {
    if (!selected) return;
    setDraft(selected.status === "已回复" ? "已完成回复，可继续编辑" : selected.category === "情绪支持" ? "听起来你最近承受了不少压力，谢谢你愿意把这份感受说出来。可以先从今天最困扰你的一个小片段开始，给自己一点喘息的空间；如果这种疲惫持续影响生活，也建议找专业咨询师聊聊。" : "感谢你的留言，我们会把这个问题记录下来并持续完善。你也可以告诉我们更具体的使用场景。 ");
  }, [selectedId, selected?.status, selected?.category]);

  // 中文说明：函数「sendReply」负责完成该界面的状态处理、交互逻辑或数据转换。
  function sendReply() {
    if (!selected || !draft.trim() || selected.status === "已回复") return;
    setComments((items) => items.map((item) => item.id === selected.id ? { ...item, status: "已回复" } : item));
  }

  return (
    <div className="engagement-layout">
      <section className="panel engagement-queue">
        <div className="panel-heading tight">
          <div><h2>待处理互动</h2><p>按主题分派给对应员工，回复前请先确认语气和安全边界。</p></div>
          <span className="count-badge">{comments.filter((item) => item.status === "待回复").length} 待回复</span>
        </div>
        <div className="comment-list">
          {comments.map((comment) => (
            <button type="button" key={comment.id} className={cn("comment-row", selectedId === comment.id && "selected")} onClick={() => setSelectedId(comment.id)}>
              <div className="comment-avatar">{comment.author.slice(0, 1)}</div>
              <div className="comment-main"><div className="comment-meta"><strong>{comment.author}</strong><span>{comment.time}</span></div><p>{comment.content}</p><div className="comment-tags"><span>{comment.category}</span><span className={comment.priority === "高" ? "priority-high" : ""}>{comment.priority}</span></div></div>
              <div className={cn("reply-owner", comment.status === "已回复" && "replied")}><HeartHandshake size={14} /><span>{agentName(comment.assignedAgentId)}</span></div>
            </button>
          ))}
        </div>
      </section>
      <section className="panel reply-panel">
        {selected && <>
          <div className="panel-heading tight"><div><h2>回复工作台</h2><p>{selected.source}</p></div><span className={cn("reply-status", selected.status === "已回复" && "done")}>{selected.status}</span></div>
          <div className="selected-comment"><strong>{selected.author}</strong><p>{selected.content}</p></div>
          <label className="reply-label"><span>负责员工</span><select value={selected.assignedAgentId} onChange={(event) => setComments((items) => items.map((item) => item.id === selected.id ? { ...item, assignedAgentId: event.target.value } : item))}>{agents.filter((agent) => ["healer", "operator", "product_manager"].includes(agent.id)).map((agent) => <option key={agent.id} value={agent.id}>{agent.title}</option>)}</select></label>
          <label className="reply-label"><span>回复内容</span><textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={7} /></label>
          <div className="reply-footer"><span><MessageCircle size={15} /> 建议由 {agentName(selected.assignedAgentId)} 回复</span><button className="primary-button" type="button" onClick={sendReply} disabled={selected.status === "已回复" || !draft.trim()}>{selected.status === "已回复" ? "已提交" : "提交回复"}</button></div>
        </>}
      </section>
    </div>
  );
}

// 中文说明：函数「StockAnalysisView」负责完成该界面的状态处理、交互逻辑或数据转换。
function StockAnalysisView() {
  const [stocks, setStocks] = useState("600519");
  const [result, setResult] = useState<StockAnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [health, setHealth] = useState<{ status: string; libraries: Record<string, string>; credentials: Record<string, string>; retry_limit: number; cache_ttl_seconds: number } | null>(null);

  useEffect(() => {
    fetchStockSourcesHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  async function handleAnalyze() {
    setBusy(true);
    setMessage(null);
    try {
      setResult(await analyzeStocks({ stocks }));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "股票分析失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="single-view">
      <section className="panel action-panel">
        <div className="panel-heading">
          <div>
            <h2>股票助手 · Stock Analysis Skill</h2>
            <p>财经、股票和股票新闻请求默认调用此 Skill。支持 A 股、港股、美股。</p>
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。
          {/* 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
          </div>
          <button className="primary-button" onClick={handleAnalyze} disabled={busy || !stocks.trim()} type="button">
            {busy ? <Loader2 className="spin" size={18} /> : <TrendingUp size={18} />}
            <span>{busy ? "分析中" : "开始分析"}</span>
          </button>
        </div>
        <div className="form-grid">
          <label className="wide">
            <span>股票代码或名称（逗号分隔）</span>
            <input value={stocks} onChange={(event) => setStocks(event.target.value)} placeholder="600519, TSLA, HK00700" />
          </label>
        </div>
        {health && <div className="control-message"><CheckCircle2 size={16} /><span>数据源：{health.status === "ok" ? "可用" : "暂不可用"} · 重试 {health.retry_limit} 次 · 缓存 {health.cache_ttl_seconds} 秒</span></div>}
        {message && <div className="control-message"><AlertCircle size={16} /><span>{message}</span></div>}
      </section>
      {result && (
        <section className="panel outputs-panel">
          <div className="panel-heading tight">
            <div>
              <h2>股票决策看板</h2>
              <p>数据脚本：{result.data_script} · 新闻抓取：{result.news_enabled ? "已启用" : "未启用"}</p>
            </div>
          </div>
          {result.data_status && <div className={cn("stock-data-status", result.data_status)}>{result.data_status === "ok" ? "数据完整" : result.data_status === "partial" ? "部分数据可用" : "数据暂不可用"}{result.source_status?.cache === "hit" ? " · 使用缓存" : ""}</div>}
          <MarkdownContent content={result.report} className="stock-report-markdown" />
          <p className="risk-note">{result.disclaimer}</p>
        </section>
      )}
    </div>
  );
}

type ControlAction = "backend-start" | "backend-stop" | "backend-restart" | "frontend-stop";

// 中文说明：函数「ServiceCard」负责完成该界面的状态处理、交互逻辑或数据转换。
function ServiceCard({
  service,
  busyAction,
  onAction
}: {
  service: ManagedServiceStatus;
  busyAction: ControlAction | null;
  onAction: (action: ControlAction) => void;
}) {
  const isBackend = service.name === "backend";
  const Icon = isBackend ? Server : Cpu;
  const stopAction = isBackend ? "backend-stop" : "frontend-stop";

  return (
    <article className="service-card">
      <div className="service-head">
        <div className="service-title">
          <div className="stage-icon">
            <Icon size={18} />
          </div>
          <div>
            <strong>{isBackend ? "后端服务" : "前端服务"}</strong>
            <span>{service.url}</span>
          </div>
        </div>
        <span className={cn("service-status", service.running && "online", !service.running && service.port_occupied && "occupied")}>
          {service.running ? "运行中" : service.port_occupied ? "端口占用" : "已关闭"}
        </span>
      </div>

      <div className="service-meta">
        <div>
          <span>端口</span>
          <strong>{service.port}</strong>
        </div>
        <div>
          <span>进程</span>
          <strong>{service.processes.length ? service.processes.map((item) => item.pid).join(" / ") : "无"}</strong>
        </div>
      </div>
      {/* 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。

      <div className="service-process-list">
        {service.processes.length ? (
          service.processes.map((process) => (
            <div key={`${service.name}-${process.pid}`}>
              <strong>
                PID {process.pid} · {process.name}
              </strong>
              <span>{process.project_owned ? "本项目进程" : "非本项目进程"}</span>
            </div>
          ))
        ) : (
          <div>
            <strong>{service.running ? "当前服务进程" : "端口空闲"}</strong>
            <span>{service.running ? "由当前控制台提供服务" : "没有检测到监听进程"}</span>
          </div>
        )}
      </div>

      <div className="service-actions">
        {isBackend && (
          <>
            <button className="ghost-button compact" onClick={() => onAction("backend-start")} disabled={!service.can_start || busyAction !== null}>
              {busyAction === "backend-start" ? <Loader2 className="spin" size={16} /> : <Power size={16} />}
              <span>启动后端</span>
            </button>
            <button className="ghost-button compact" onClick={() => onAction("backend-restart")} disabled={busyAction !== null}>
              {busyAction === "backend-restart" ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
              <span>重启后端</span>
            </button>
          </>
        )}
        <button className="danger-button compact" onClick={() => onAction(stopAction)} disabled={!service.can_stop || busyAction !== null}>
          {busyAction === stopAction ? <Loader2 className="spin" size={16} /> : <Square size={16} />}
          <span>{isBackend ? "关闭后端" : "关闭前端"}</span>
        </button>
      </div>
    </article>
  );
}

// 中文说明：函数「SettingsView」负责完成该界面的状态处理、交互逻辑或数据转换。
function SettingsView({ status, currentRun, onImport, onBackendStateChange, systemStatusSnapshot, onSystemStatusSnapshotChange, viralAnalysis, onViralAnalysisChange }: { status: ApiStatus | null; currentRun: WorkflowRun | null; onImport: (run: WorkflowRun) => void; onBackendStateChange: () => void; systemStatusSnapshot: SystemStatus | null; onSystemStatusSnapshotChange: (status: SystemStatus) => void; viralAnalysis: ViralAnalysisConfig; onViralAnalysisChange: (config: ViralAnalysisConfig) => void }) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(systemStatusSnapshot);
  const [controlBusy, setControlBusy] = useState<ControlAction | null>(null);
  const [controlMessage, setControlMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [timeoutSettings, setTimeoutSettings] = useState<TimeoutSettings | null>(null);
  const [timeoutDraft, setTimeoutDraft] = useState<TimeoutSettings>(defaultTimeoutSettings);
  const [unlimitedTimeouts, setUnlimitedTimeouts] = useState({ news: false, model: false });
  const [timeoutBusy, setTimeoutBusy] = useState(false);
  const [timeoutMessage, setTimeoutMessage] = useState<string | null>(null);
  const [outputDirs, setOutputDirs] = useState<OutputDirectorySettings>({ video_output_dir: "", operator_output_dir: "" });
  const [outputDirBusy, setOutputDirBusy] = useState(false);
  const [outputDirMessage, setOutputDirMessage] = useState<string | null>(null);
  const [envSettings, setEnvSettings] = useState<EnvSettings | null>(null);
  const [envDraft, setEnvDraft] = useState({ ai_api_key: "", ai_base_url: "", ai_model: "", mpt_pexels_api_key: "", backend_port: 8017, socialdatax_api_key: "", socialdatax_base_url: "", socialdatax_timeout_seconds: 60, tushare_token: "", tavily_api_key: "", serpapi_key: "" });
  const [envBusy, setEnvBusy] = useState(false);
  const [envMessage, setEnvMessage] = useState<string | null>(null);
  const [activeEnvCategory, setActiveEnvCategory] = useState<"ai" | "other" | "optional" | null>(null);

  // 中文说明：函数「applyTimeoutSettings」负责完成该界面的状态处理、交互逻辑或数据转换。
  function applyTimeoutSettings(next: TimeoutSettings) {
    setTimeoutSettings(next);
    setTimeoutDraft({
      news_fetch_timeout_seconds: next.news_fetch_timeout_seconds || defaultTimeoutSettings.news_fetch_timeout_seconds,
      model_timeout_seconds: next.model_timeout_seconds || defaultTimeoutSettings.model_timeout_seconds,
      workflow_timeout_seconds: next.workflow_timeout_seconds || defaultTimeoutSettings.workflow_timeout_seconds
    });
    setUnlimitedTimeouts({
      news: next.news_fetch_timeout_seconds === 0,
      model: next.model_timeout_seconds === 0
    });
  }

  // 中文说明：函数「updateTimeoutDraft」负责完成该界面的状态处理、交互逻辑或数据转换。
  function updateTimeoutDraft(field: keyof TimeoutSettings, value: string) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setTimeoutDraft((current) => ({ ...current, [field]: Math.max(1, Math.floor(parsed)) }));
  }

  // 中文说明：函数「toggleUnlimited」负责完成该界面的状态处理、交互逻辑或数据转换。
  function toggleUnlimited(field: "news" | "model", enabled: boolean) {
    setUnlimitedTimeouts((current) => ({ ...current, [field]: enabled }));
    if (!enabled) {
      const draftField = field === "news" ? "news_fetch_timeout_seconds" : "model_timeout_seconds";
      setTimeoutDraft((current) => ({
        ...current,
        [draftField]: current[draftField] || defaultTimeoutSettings[draftField]
      }));
    }
  }

  async function handleTimeoutSave() {
    setTimeoutBusy(true);
    setTimeoutMessage(null);
    try {
      const saved = await updateTimeoutSettings({
        news_fetch_timeout_seconds: unlimitedTimeouts.news ? 0 : timeoutDraft.news_fetch_timeout_seconds,
        model_timeout_seconds: unlimitedTimeouts.model ? 0 : timeoutDraft.model_timeout_seconds,
        workflow_timeout_seconds: timeoutDraft.workflow_timeout_seconds
      });
      applyTimeoutSettings(saved);
      setTimeoutMessage("热点扫描超时设置已保存");
    } catch (err) {
      setTimeoutMessage(err instanceof Error ? err.message : "保存超时设置失败");
    } finally {
      setTimeoutBusy(false);
    }
  }

  async function handleExport() {
    if (!currentRun) { setControlMessage("当前没有可导出的项目"); return; }
    try {
      const data = await exportWorkflow(currentRun.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `signalforge-${currentRun.id}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setControlMessage("项目已导出");
    } catch (err) { setControlMessage(err instanceof Error ? err.message : "导出失败"); }
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    try {
      const imported = await importWorkflow(file);
      onImport(imported);
      // Keep the selected topic and browser checkpoint in sync immediately;
      // otherwise the overview can be overwritten by stale local state.
      setControlMessage("项目已导入");
    }
    catch (err) { setControlMessage(err instanceof Error ? err.message : "导入失败"); }
  }

  async function refreshSystemStatus() {
    const next = await fetchSystemStatus();
    setSystemStatus(next);
    onSystemStatusSnapshotChange(next);
    // A transient PowerShell/WMI failure should not remain pinned in the
    // panel after a later refresh succeeds.
    setControlMessage(null);
    return next;
  }

  useEffect(() => {
    if (systemStatusSnapshot) setSystemStatus(systemStatusSnapshot);
  }, [systemStatusSnapshot]);

  useEffect(() => {
    if (!systemStatusSnapshot) refreshSystemStatus().catch((err: Error) => setControlMessage(err.message));
  }, []);

  useEffect(() => {
    fetchOutputDirectorySettings().then(setOutputDirs).catch((err: Error) => setOutputDirMessage(err.message));
  }, []);

  useEffect(() => {
    fetchEnvSettings().then((next) => {
      setEnvSettings(next);
      setEnvDraft((current) => ({ ...current, ai_base_url: next.ai_base_url, ai_model: next.ai_model, backend_port: next.backend_port, socialdatax_base_url: next.socialdatax_base_url, socialdatax_timeout_seconds: next.socialdatax_timeout_seconds }));
    }).catch((err: Error) => setEnvMessage(err.message));
  }, []);

  async function handleEnvSave() {
    setEnvBusy(true); setEnvMessage(null);
    try {
      const saved = await updateEnvSettings(envDraft);
      const savedDirs = await updateOutputDirectorySettings(outputDirs);
      setEnvSettings(saved);
      setOutputDirs(savedDirs);
      setEnvDraft((current) => ({ ...current, ai_api_key: "", mpt_pexels_api_key: "", socialdatax_api_key: "", tushare_token: "", tavily_api_key: "", serpapi_key: "", ai_base_url: saved.ai_base_url, ai_model: saved.ai_model, backend_port: saved.backend_port, socialdatax_base_url: saved.socialdatax_base_url, socialdatax_timeout_seconds: saved.socialdatax_timeout_seconds }));
      setEnvMessage("运行配置已保存；密钥仅在填写新值时更新");
      onBackendStateChange();
    } catch (err) { setEnvMessage(err instanceof Error ? err.message : "保存运行配置失败"); }
    finally { setEnvBusy(false); }
  }

  async function handleOutputDirSave() {
    setOutputDirBusy(true); setOutputDirMessage(null);
    try {
      const saved = await updateOutputDirectorySettings(outputDirs);
      setOutputDirs(saved); setOutputDirMessage("产物目录已保存");
    } catch (err) { setOutputDirMessage(err instanceof Error ? err.message : "保存产物目录失败"); }
    finally { setOutputDirBusy(false); }
  }

  async function handleDirectorySelect(field: keyof OutputDirectorySettings) {
    try {
      const selected = await selectDirectory();
      if (selected.path) setOutputDirs((current) => ({ ...current, [field]: selected.path }));
    } catch (err) { setEnvMessage(err instanceof Error ? err.message : "选择目录失败"); }
  }

  useEffect(() => {
    fetchTimeoutSettings()
      .then(applyTimeoutSettings)
      .catch((err: Error) => setTimeoutMessage(err.message));
  }, []);

  async function handleControl(action: ControlAction) {
    const confirmation =
      action === "frontend-stop"
        ? "关闭前端后，当前页面会失去响应，5173 端口将被释放。确定继续吗？"
        : action === "backend-stop"
          ? "关闭后端会中断正在运行的工作流和 API 请求。确定继续吗？"
          : action === "backend-restart"
            ? "重启后端会短暂中断 API 请求。确定继续吗？"
            : null;
    if (confirmation && !window.confirm(confirmation)) {
      return;
    }

    setControlBusy(action);
    setControlMessage(null);
    try {
      const result =
        action === "backend-start"
          ? await startBackend()
          : action === "backend-stop"
            ? await stopBackend()
            : action === "backend-restart"
              ? await restartBackend()
              : await stopFrontend();
      setControlMessage(result.message);
      if (result.status) {
        setSystemStatus(result.status);
        onSystemStatusSnapshotChange(result.status);
      } else if (action !== "frontend-stop") {
        await refreshSystemStatus();
      }
      if (action.startsWith("backend-")) {
        onBackendStateChange();
      }
    } catch (err) {
      setControlMessage(err instanceof Error ? err.message : "控制命令失败");
    } finally {
      setControlBusy(null);
    }
  }
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。

  return (
    <div className={`single-view settings-page-shell${activeEnvCategory ? " subpage" : ""}`}>
      <div className="settings-overview-grid">
      <section className="panel settings-panel runtime-settings-panel">
        <div className="panel-heading tight"><div><h2>运行配置</h2><p>仅显示已配置密钥的首尾字符，中间内容始终打码。</p></div></div>
        <div className="settings-list">
          <div><KeyRound size={18} /><span>Key Path</span><strong>{status?.key_preview ?? "未配置"}</strong></div>
          <div><ExternalLink size={18} /><span>Base URL</span><strong>{status?.base_url ?? "https://api.openlux.ai/v1"}</strong></div>
          <div><Bot size={18} /><span>Model</span><strong>{status?.model ?? "中转站自动选择"}</strong></div>
          <div><FileText size={18} /><span>AI Health</span><strong>{status ? (status.model_available ? "模型可用" : "模型不可用") : "检查中"}</strong></div>
        </div>
      </section>
      <section className="panel settings-panel project-settings-panel">
        <div className="panel-heading tight">
          <div><h2>项目文件</h2><p>手动保存或恢复热点、产物和流水线进度。</p></div>
        </div>
        <div className="project-file-actions">
          <button className="primary-button" type="button" onClick={handleExport}><FileText size={17} /><span>导出项目</span></button>
          <button className="ghost-button" type="button" onClick={() => fileInputRef.current?.click()}><RefreshCcw size={17} /><span>导入项目</span></button>
          <input ref={fileInputRef} type="file" accept="application/json,.json" hidden onChange={(event) => handleImport(event.target.files?.[0])} />
        </div>
      </section>
      <section className="panel settings-panel project-config-panel">
        <div className="panel-heading tight"><div><h2>项目配置</h2><p>管理本项目的运行参数和可选服务。</p></div></div>
        <div className="env-category-actions">
          <button className="ghost-button" type="button" onClick={() => setActiveEnvCategory("ai")}><Bot size={17} /><span>AI 配置</span></button>
          <button className="ghost-button" type="button" onClick={() => setActiveEnvCategory("other")}><Server size={17} /><span>其他配置</span></button>
          <button className="ghost-button" type="button" onClick={() => setActiveEnvCategory("optional")}><Plus size={17} /><span>可选配置</span></button>
        </div>
      </section>
      </div>
      {activeEnvCategory && <section className="panel settings-panel env-settings-panel" data-category={activeEnvCategory}>
        <div className="panel-heading tight"><div><h2>{activeEnvCategory === "ai" ? "AI 配置" : activeEnvCategory === "other" ? "其他配置" : "可选配置"}</h2><p>已配置密钥只显示掩码；密钥输入框留空表示保留原值。端口变更需重启后端后生效。</p></div><button className="ghost-button inline" type="button" onClick={() => setActiveEnvCategory(null)}>返回项目设置</button></div>
        <div className="timeout-grid">
          <label className="timeout-field"><span className="timeout-label">AI Base URL</span><input value={envDraft.ai_base_url} onChange={(e) => setEnvDraft({ ...envDraft, ai_base_url: e.target.value })} placeholder="https://api.openlux.ai/v1" /></label>
          <label className="timeout-field"><span className="timeout-label">AI Model</span><input value={envDraft.ai_model} onChange={(e) => setEnvDraft({ ...envDraft, ai_model: e.target.value })} placeholder="留空自动选择" /></label>
          <label className="timeout-field"><span className="timeout-label">后端端口</span><input type="number" min="1" max="65535" value={envDraft.backend_port} onChange={(e) => setEnvDraft({ ...envDraft, backend_port: Number(e.target.value) || 8017 })} /></label>
          <label className="timeout-field"><span className="timeout-label">AI API Key {envSettings?.ai_api_key.configured && <small><br />（当前 {envSettings.ai_api_key.preview}）</small>}</span><input type="password" value={envDraft.ai_api_key} onChange={(e) => setEnvDraft({ ...envDraft, ai_api_key: e.target.value })} placeholder="留空保留现有密钥" autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">Pexels Key {envSettings?.mpt_pexels_api_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.mpt_pexels_api_key} onChange={(e) => setEnvDraft({ ...envDraft, mpt_pexels_api_key: e.target.value })} placeholder="可选" autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">SocialDataX Base URL</span><input value={envDraft.socialdatax_base_url} onChange={(e) => setEnvDraft({ ...envDraft, socialdatax_base_url: e.target.value })} /></label>
          <label className="timeout-field"><span className="timeout-label">SocialDataX API Key {envSettings?.socialdatax_api_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.socialdatax_api_key} onChange={(e) => setEnvDraft({ ...envDraft, socialdatax_api_key: e.target.value })} placeholder="可选" autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">SocialDataX 超时（秒）</span><input type="number" min="0" value={envDraft.socialdatax_timeout_seconds} onChange={(e) => setEnvDraft({ ...envDraft, socialdatax_timeout_seconds: Math.max(0, Number(e.target.value) || 0) })} /></label>
          {activeEnvCategory === "other" && <>
            <div className="timeout-field directory-field"><span className="timeout-label">视频输出目录</span><div className="directory-picker-row"><span className="directory-value">{outputDirs.video_output_dir || "未选择"}</span><button className="ghost-button" type="button" onClick={() => handleDirectorySelect("video_output_dir")}>选择目录</button></div><span className="timeout-hint">MP4 成片及视频剪辑产物</span></div>
            <div className="timeout-field directory-field"><span className="timeout-label">运营大师输出目录</span><div className="directory-picker-row"><span className="directory-value">{outputDirs.operator_output_dir || "未选择"}</span><button className="ghost-button" type="button" onClick={() => handleDirectorySelect("operator_output_dir")}>选择目录</button></div><span className="timeout-hint">标题、封面文案、发布时间和复盘指标</span></div>
            <div className="other-config-block">
              <div className="other-config-heading"><div><strong>爆款分析</strong><span>这里只影响总控制台流水线；<br />员工独立工作台有各自设置。</span></div></div>
              <label className="switch-line switch-control"><input type="checkbox" checked={viralAnalysis.enabled} onChange={(event) => onViralAnalysisChange({ ...viralAnalysis, enabled: event.target.checked })} /><span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span><span className="switch-copy"><strong>{viralAnalysis.enabled ? "已启用" : "已关闭"}</strong><small>控制台流水线是否执行爆款分析阶段</small></span></label>
              <div className="segmented-control"><button className={cn("segment-button", viralAnalysis.source === "socialdatax" && "selected")} onClick={() => onViralAnalysisChange({ ...viralAnalysis, source: "socialdatax" })} type="button">SocialDataX</button><button className={cn("segment-button", viralAnalysis.source === "manual" && "selected")} onClick={() => onViralAnalysisChange({ ...viralAnalysis, source: "manual" })} type="button">手写分析</button></div>
              {viralAnalysis.source === "manual" && <label><span>手写分析依据</span><textarea value={viralAnalysis.manual_content} onChange={(event) => onViralAnalysisChange({ ...viralAnalysis, manual_content: event.target.value })} placeholder="填写总控制台本轮使用的样本或分析依据" /></label>}
            </div>
          </>}
        </div>
        <details className="env-advanced"><summary>股票新闻服务密钥（可选）</summary><div className="timeout-grid">
          <label className="timeout-field"><span className="timeout-label">Tushare Token {envSettings?.tushare_token.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.tushare_token} onChange={(e) => setEnvDraft({ ...envDraft, tushare_token: e.target.value })} autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">Tavily API Key {envSettings?.tavily_api_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.tavily_api_key} onChange={(e) => setEnvDraft({ ...envDraft, tavily_api_key: e.target.value })} autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">SerpAPI Key {envSettings?.serpapi_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.serpapi_key} onChange={(e) => setEnvDraft({ ...envDraft, serpapi_key: e.target.value })} autoComplete="new-password" /></label>
        </div></details>
        <div className="timeout-actions"><button className="primary-button" type="button" onClick={handleEnvSave} disabled={envBusy || !envSettings}><Save size={17} /><span>{envBusy ? "保存中" : "保存运行配置"}</span></button>{envMessage && <span className="timeout-message">{envMessage}</span>}</div>
      </section>}
      {false && <section className="panel settings-panel output-directory-panel">
        <div className="panel-heading tight"><div><h2>产物输出目录</h2><p>可填写绝对路径；留空则使用项目默认目录。视频会复制到视频目录，运营大师的标题、封面文案和复盘指标会保存到运营目录。</p></div></div>
        <div className="timeout-grid">
          <label className="timeout-field"><span className="timeout-label">视频输出目录</span><input value={outputDirs.video_output_dir} onChange={(event) => setOutputDirs({ ...outputDirs, video_output_dir: event.target.value })} placeholder="例如 D:\\Videos\\SignalForge" /><span className="timeout-hint">MP4 成片及视频剪辑产物</span></label>
          <label className="timeout-field"><span className="timeout-label">运营大师输出目录</span><input value={outputDirs.operator_output_dir} onChange={(event) => setOutputDirs({ ...outputDirs, operator_output_dir: event.target.value })} placeholder="例如 D:\\Content\\运营方案" /><span className="timeout-hint">标题、封面文案、发布时间和复盘指标</span></label>
        </div>
        <div className="timeout-actions"><button className="primary-button" type="button" onClick={handleOutputDirSave} disabled={outputDirBusy}><Save size={17} /><span>{outputDirBusy ? "保存中" : "保存产物目录"}</span></button>{outputDirMessage && <span className="timeout-message">{outputDirMessage}</span>}</div>
      </section>}
      <div className="settings-management-grid">
      <section className="panel settings-panel timeout-settings-panel">
        <div className="panel-heading tight">
          <div>
            <h2>热点扫描超时</h2>
            <p>控制公开来源抓取和模型整理的等待时间，0 表示不限时；视频剪辑员成片渲染始终不限时。</p>
          </div>
        </div>
        <div className="timeout-grid">
          <label className="timeout-field">
            <span className="timeout-label">公开来源抓取</span>
            <div className="timeout-input-row">
              <input
                type="number"
                min="1"
                step="1"
                value={unlimitedTimeouts.news ? "" : timeoutDraft.news_fetch_timeout_seconds}
                disabled={timeoutSettings === null || unlimitedTimeouts.news}
                onChange={(event) => updateTimeoutDraft("news_fetch_timeout_seconds", event.target.value)}
              />
              <span>秒</span>
            </div>
            <span className="timeout-hint">Skill 多来源抓取</span>
            <span className="timeout-toggle">
              <input
                type="checkbox"
                checked={unlimitedTimeouts.news}
                disabled={timeoutSettings === null}
                onChange={(event) => toggleUnlimited("news", event.target.checked)}
              />
              <span>不限时</span>
            </span>
          </label>
          <label className="timeout-field">
            <span className="timeout-label">工作流总时限</span>
            <div className="timeout-input-row">
              <input
                type="number"
                min="1"
                max="86400"
                step="1"
                value={timeoutDraft.workflow_timeout_seconds}
                disabled={timeoutSettings === null}
                onChange={(event) => updateTimeoutDraft("workflow_timeout_seconds", event.target.value)}
              />
              <span>秒</span>
            </div>
            <span className="timeout-hint">超时后保留检查点，可继续执行</span>
          </label>
          <label className="timeout-field">
            <span className="timeout-label">模型整理</span>
            <div className="timeout-input-row">
              <input
                type="number"
                min="1"
                step="1"
                value={unlimitedTimeouts.model ? "" : timeoutDraft.model_timeout_seconds}
                disabled={timeoutSettings === null || unlimitedTimeouts.model}
                onChange={(event) => updateTimeoutDraft("model_timeout_seconds", event.target.value)}
              />
              <span>秒</span>
            </div>
            <span className="timeout-hint">AI 生成热点候选</span>
            <span className="timeout-toggle">
              <input
                type="checkbox"
                checked={unlimitedTimeouts.model}
                disabled={timeoutSettings === null}
                onChange={(event) => toggleUnlimited("model", event.target.checked)}
              />
              <span>不限时</span>
            </span>
          </label>
        </div>
        <div className="timeout-actions">
          <button className="primary-button" type="button" onClick={handleTimeoutSave} disabled={timeoutBusy || timeoutSettings === null}>
            <Save size={17} />
            <span>{timeoutBusy ? "保存中" : "保存超时设置"}</span>
          </button>
          {timeoutMessage && <span className="timeout-message">{timeoutMessage}</span>}
        </div>
      </section>
      <section className="panel service-panel">
        <div className="panel-heading tight">
          <div>
            <h2>本地服务控制</h2>
            <p>查看端口占用，启动、关闭或重启本项目的后端和前端。</p>
          </div>
          <button className="ghost-button inline" onClick={() => refreshSystemStatus().catch((err: Error) => setControlMessage(err.message))} disabled={controlBusy !== null}>
            <RefreshCcw size={16} />
            <span>刷新状态</span>
          </button>
        </div>
        {controlMessage && (
          <div className="control-message">
            <CircleDot size={16} />
            <span>{controlMessage}</span>
          </div>
        )}
        <div className="service-grid">
          {systemStatus ? (
            <>
              <ServiceCard service={systemStatus.backend} busyAction={controlBusy} onAction={handleControl} />
              <ServiceCard service={systemStatus.frontend} busyAction={controlBusy} onAction={handleControl} />
            </>
          ) : (
            <div className="empty-state">
              <Loader2 className="spin" size={20} />
              <span>正在读取本地服务状态。</span>
            </div>
          )}
        </div>
      </section>
      </div>
    </div>
  );
}

// 中文说明：函数「OverviewView」负责完成该界面的状态处理、交互逻辑或数据转换。
function OverviewView({
  run,
  running,
  seed,
  setSeed,
  agents,
  outputs,
  onNew,
  onStep,
  onCancel,
  onRerun,
  onOpenArtifacts,
  selectedTopicTitle,
  onSelectTopic
}: {
  run: WorkflowRun | null;
  running: boolean;
  seed: TopicSeed;
  setSeed: (seed: TopicSeed) => void;
  agents: Agent[];
  outputs: AgentOutput[];
  onNew: () => void;
  onStep: () => void;
  onCancel: () => void;
  onRerun: (stage: string) => void;
  onOpenArtifacts: () => void;
  selectedTopicTitle: string | null;
  onSelectTopic: (title: string | null) => void;
}) {
  return (
    <div className="content-grid">
      <div className="left-stack">
        <PipelineBoard run={run} running={running} onNew={onNew} onStep={onStep} onCancel={onCancel} onRerun={onRerun} onOpenArtifacts={onOpenArtifacts} />
        <TopicList run={run} selectable={run?.status === "paused" && run.stage_status?.hotspot_monitor === "completed" && run.stage_status?.viral_analyst !== "completed"} selectedTitle={selectedTopicTitle} onSelect={onSelectTopic} />
        <OutputList outputs={outputs} />
      </div>
      <div className="right-stack">
        <SeedPanel
          seed={seed}
          onChange={setSeed}
        />
        <AgentRoster agents={agents} />
      </div>
    </div>
  );
}

// 中文说明：函数「App」负责完成该界面的状态处理、交互逻辑或数据转换。
export default function App() {
  const [activeView, setActiveView] = useState<ViewId>(readSavedView);
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [seed, setSeed] = useState<TopicSeed>(() => ({
    ...defaultSeed,
    ...readSaved<Partial<TopicSeed>>("signalforge.seed", {})
  }));
  const [viralAnalysis, setViralAnalysis] = useState<ViralAnalysisConfig>(readViralAnalysis);
  const [run, setRun] = useState<WorkflowRun | null>(readSavedRun);
  const [selectedTopicTitle, setSelectedTopicTitle] = useState<string | null>(() => readSaved< string | null>("signalforge.selectedTopicTitle", null));
  const [radarTopics, setRadarTopics] = useState<Topic[]>([]);
  const [running, setRunning] = useState(false);
  const [closing, setClosing] = useState(false);
  const [shutdownComplete, setShutdownComplete] = useState(false);
  const [systemStatusSnapshot, setSystemStatusSnapshot] = useState<SystemStatus | null>(null);
  const [settingsStripCollapsed, setSettingsStripCollapsed] = useState(false);

  // Keep local service state warm while the app is open, instead of waiting
  // for the Settings view to mount and issuing its first expensive query.
  useEffect(() => {
    let disposed = false;
    // 中文说明：函数「refresh」负责完成该界面的状态处理、交互逻辑或数据转换。
    const refresh = () => {
      fetchSystemStatus().then((next) => {
        if (!disposed) setSystemStatusSnapshot(next);
      }).catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);
  const [error, setError] = useState<string | null>(null);
  const [agentTaskStatuses, setAgentTaskStatuses] = useState<Record<string, AgentTaskStatus>>({});
  const [agentErrors, setAgentErrors] = useState<Record<string, string | null>>({});
  const [agentOutputs, setAgentOutputs] = useState<Record<string, AgentOutput | null>>(() => readSaved("signalforge.employee.outputs", {}));
  const [agentLogs, setAgentLogs] = useState<Record<string, AgentTaskLog[]>>({});
  const importedRunRef = useRef<string | null>(null);

  useEffect(() => {
    const agentId = employeeIdFromView(activeView);
    if (!agentId) return;
    fetchAgentLogs(agentId).then((logs) => {
      setAgentLogs((current) => ({ ...current, [agentId]: logs }));
      setAgentTaskStatuses((current) => {
        if (current[agentId] === "running") return current;
        const latest = logs.at(-1);
        const taskStatus = latest?.level === "success"
          ? "completed"
          : latest?.level === "error"
            ? "failed"
            : latest?.level === "info"
              ? "running"
              : "idle";
        return { ...current, [agentId]: taskStatus };
      });
    }).catch(() => undefined);
  }, [activeView]);
  useEffect(() => { window.localStorage.setItem("signalforge.employee.outputs", JSON.stringify(agentOutputs)); }, [agentOutputs]);

  // Standalone workbench results are project artifacts as well as a local
  // cache, so importing/loading a project restores them into each workbench.
  useEffect(() => {
    if (!run?.standalone_outputs?.length) return;
    setAgentOutputs((current) => {
      const next = { ...current };
      for (const output of run.standalone_outputs ?? []) next[output.agent_id] = output;
      return next;
    });
  }, [run?.id, run?.standalone_outputs]);

  const outputs = useMemo(() => {
    return run?.outputs ?? [];
  }, [run]);

  async function refreshBackendData(options: { showErrors?: boolean } = {}) {
    try {
      const [apiStatus, apiAgents] = await Promise.all([fetchStatus(), fetchAgents()]);
      setStatus(apiStatus);
      setAgents(apiAgents);
      setError(null);
    } catch (err) {
      setStatus(null);
      setAgents([]);
      if (options.showErrors) {
        setError(err instanceof Error ? err.message : "后端请求失败");
      }
    }
  }

  useEffect(() => {
    refreshBackendData();
    fetchWorkflows().then((items) => {
      // Do not let the initial list request overwrite a project that the user
      // has just imported in the settings view.
      if (items.length && !importedRunRef.current) setRun(items[0]);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("signalforge.seed", JSON.stringify(seed));
  }, [seed]);

  useEffect(() => {
    window.localStorage.setItem("signalforge.activeView", JSON.stringify(activeView));
  }, [activeView]);

  useEffect(() => {
    window.localStorage.setItem("signalforge.viralAnalysis", JSON.stringify(viralAnalysis));
  }, [viralAnalysis]);

  useEffect(() => {
    if (run) window.localStorage.setItem("signalforge.currentRun", JSON.stringify(run));
  }, [run]);

  useEffect(() => {
    window.localStorage.setItem("signalforge.selectedTopicTitle", JSON.stringify(selectedTopicTitle));
  }, [selectedTopicTitle]);

  useEffect(() => {
    if (run?.status === "failed" && run.error) {
      setError(formatWorkflowError(run));
    }
  }, [run?.status, run?.error, run?.current_stage]);

  async function waitForRun(initial: WorkflowRun): Promise<WorkflowRun> {
    let current = initial;
    setRun(current);
    while (current.status === "queued" || current.status === "running") {
      await new Promise((resolve) => window.setTimeout(resolve, 700));
      current = await fetchWorkflow(current.id);
      setRun(current);
    }
    return current;
  }

  // 中文说明：函数「showRunError」负责完成该界面的状态处理、交互逻辑或数据转换。
  function showRunError(result: WorkflowRun, fallback: string) {
    if (result.status === "failed") {
      setError(formatWorkflowError(result, fallback));
    }
  }

  async function handleSingleAgent(agentId: string, prompt: string, settings: Record<string, unknown>) {
    setAgentTaskStatuses((current) => ({ ...current, [agentId]: "running" }));
    setAgentErrors((current) => ({ ...current, [agentId]: null }));
    try {
      // A standalone run still belongs to a project. If the user opened an
      // employee workbench before creating a console task, create a paused
      // project checkpoint first so this result can be exported.
      let project = run;
      if (!project) {
        project = await runHotVideoWorkflow(seed, "manual", viralAnalysis);
        setRun(project);
      }
      const timeoutSeconds = typeof settings.timeout_seconds === "number" ? settings.timeout_seconds : 300;
      const output = await runAgent(agentId, { prompt, settings, timeout_seconds: timeoutSeconds, project_run_id: project.id });
      setAgentOutputs((current) => ({ ...current, [agentId]: output }));
      setRun((current) => current ? {
        ...current,
        standalone_outputs: [
          ...(current.standalone_outputs ?? []).filter((item) => item.agent_id !== agentId),
          output,
        ],
      } : current);
      const logs = await fetchAgentLogs(agentId);
      setAgentLogs((current) => ({ ...current, [agentId]: logs }));
      setAgentTaskStatuses((current) => ({ ...current, [agentId]: "completed" }));
    } catch (err) {
      const message = err instanceof Error ? err.message : `${agentId} 执行失败`;
      setAgentTaskStatuses((current) => ({ ...current, [agentId]: "failed" }));
      setAgentErrors((current) => ({ ...current, [agentId]: message }));
    }
  }

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      const initial = run && (run.status === "queued" || run.status === "paused" || (run.status === "failed" && run.resumable))
        ? await resumeWorkflow(run.id)
        : await runHotVideoWorkflow(seed, "auto", viralAnalysis);
      const result = await waitForRun(initial);
      showRunError(result, "流水线失败，但服务端没有提供错误详情");
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作流运行失败");
    } finally {
      setRunning(false);
    }
  }
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。
  // 中文说明：中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。

  async function handleResume() {
    if (!run) return;
    setRunning(true);
    setError(null);
    try {
      const result = await waitForRun(await resumeWorkflow(run.id));
      showRunError(result, "重试后仍然失败");
    } catch (err) {
      setError(err instanceof Error ? err.message : "继续重试失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleStep() {
    setRunning(true);
    setError(null);
    try {
      const result = await waitForRun(
        run ? await stepWorkflow(run.id, selectedTopicTitle) : await runHotVideoWorkflow(seed, "step", viralAnalysis),
      );
      showRunError(result, "阶段执行失败");
    } catch (err) {
      setError(err instanceof Error ? err.message : "阶段执行失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleRerun(stage: string) {
    if (!run) return;
    setRunning(true);
    setError(null);
    try {
      const result = await waitForRun(await stepWorkflow(run.id, selectedTopicTitle, stage));
      showRunError(result, "阶段重跑失败");
    } catch (err) {
      setError(err instanceof Error ? err.message : "阶段重跑失败");
    } finally {
      setRunning(false);
    }
  }

  // 中文说明：函数「handleSelectTopic」负责完成该界面的状态处理、交互逻辑或数据转换。
  function handleSelectTopic(title: string | null) {
    setSelectedTopicTitle(title);
    setRun((current) => current ? { ...current, selected_topic_title: title } : current);
  }

  async function handleNewTask() {
    setError(null);
    try {
      // Creating a task only persists a checkpoint. Nothing starts until the
      // user explicitly clicks the run button (or executes the next step).
      const result = await runHotVideoWorkflow(seed, "manual", viralAnalysis);
      setRun(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建新任务失败");
    }
  }

  async function handleCancel() {
    if (!run || !running) return;
    try {
      const result = await cancelWorkflow(run.id);
      setRun(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "停止任务失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleRadarScan() {
    setRunning(true);
    setError(null);
    try {
      const topics = await scoutTopics(seed);
      setRadarTopics(topics);
    } catch (err) {
      setError(err instanceof Error ? err.message : "热点扫描失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleOpenArtifacts() {
    setError(null);
    try {
      const result = await openArtifactsFolder();
      // Keep the path available in the console when the native file manager
      // cannot be launched (for example on a headless development host).
      setError(null);
      void result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "打开产物文件夹失败");
    }
  }

  async function handleShutdown() {
    if (!window.confirm("将同时关闭前端和后端服务，当前页面也会随之关闭。确定继续吗？")) {
      return;
    }

    setClosing(true);
    try {
      await shutdownAll();
    } catch {
      // The frontend exits shortly after the shutdown command, so a dropped
      // connection is expected and should not prevent the local processes from stopping.
    } finally {
      setClosing(false);
      setShutdownComplete(true);
    }
  }

  return (
    <div className="app-shell">
      <ShellNav
        activeView={activeView}
        onViewChange={setActiveView}
        closing={closing}
        shutdownComplete={shutdownComplete}
        onShutdown={handleShutdown}
      />
      <main className="main">
        <TopBar
          activeView={activeView}
          status={status}
          running={running}
          onRun={() => void handleRun()}
        />
        {error && !employeeIdFromView(activeView) && (
          <div className="error-bar">
            <AlertCircle size={17} />
            <span>{error}</span>
            {run?.status === "failed" && run.resumable && (
              <button className="ghost-button" type="button" onClick={handleResume} disabled={running}>
                <RotateCcw size={15} />
                <span>继续重试</span>
              </button>
            )}
          </div>
        )}
        {activeView === "overview" && (
          <OverviewView
            run={run}
            running={running}
            seed={seed}
            setSeed={setSeed}
            agents={agents}
            outputs={outputs}
            onNew={handleNewTask}
            onStep={handleStep}
            onCancel={handleCancel}
            onRerun={handleRerun}
            onOpenArtifacts={handleOpenArtifacts}
            selectedTopicTitle={selectedTopicTitle}
            onSelectTopic={handleSelectTopic}
          />
        )}
        {activeView === "radar" && (
          <RadarView topics={radarTopics} seed={seed} onChange={setSeed} onRun={handleRadarScan} running={running} />
        )}
        {activeView === "stocks" && <StockAnalysisView />}
        {activeView === "editing" && <EditingQueueView outputs={outputs} seed={seed} />}
        {activeView === "engagement" && <EngagementView agents={agents} />}
        {activeView === "settings" && <SettingsView status={status} currentRun={run} viralAnalysis={viralAnalysis} onViralAnalysisChange={setViralAnalysis} systemStatusSnapshot={systemStatusSnapshot} onSystemStatusSnapshotChange={setSystemStatusSnapshot} onImport={(imported) => { importedRunRef.current = imported.id; setRun(imported); setSelectedTopicTitle(imported.selected_topic_title ?? null); setAgentOutputs(Object.fromEntries((imported.standalone_outputs ?? []).map((output) => [output.agent_id, output]))); }} onBackendStateChange={() => refreshBackendData()} />}
        {employeeIdFromView(activeView) && agents.find((agent) => agent.id === employeeIdFromView(activeView)) && (
          <EmployeeWorkbench
            agent={agents.find((agent) => agent.id === employeeIdFromView(activeView))!}
            seed={seed}
            viralAnalysis={viralAnalysis}
            onRun={(prompt, settings) => void handleSingleAgent(employeeIdFromView(activeView)!, prompt, settings)}
            busy={agentTaskStatuses[employeeIdFromView(activeView)!] === "running"}
            taskStatus={agentTaskStatuses[employeeIdFromView(activeView)!] ?? "idle"}
            error={agentErrors[employeeIdFromView(activeView)!] ?? null}
            output={agentOutputs[employeeIdFromView(activeView)!] ?? null}
            logs={agentLogs[employeeIdFromView(activeView)!] ?? []}
          />
        )}
        <SettingsStrip status={status} collapsed={settingsStripCollapsed} onToggle={() => setSettingsStripCollapsed((value) => !value)} />
      </main>
    </div>
  );
}
