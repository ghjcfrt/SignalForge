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
  Video
} from "lucide-react";
import {
  fetchAgents,
  fetchAgentLogs,
  fetchWorkflow,
  fetchWorkflows,
  cancelWorkflow,
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
  ,EngagementComment
  ,TimeoutSettings
  ,ViralAnalysisConfig
  ,OutputDirectorySettings
  ,EnvSettings
  ,AgentTaskLog
} from "./types";
import ServiceCard, { type ControlAction } from "./components/ServiceCard";
import StockAnalysisViewPanel from "./components/StockAnalysisView";
import MarkdownContent from "./components/MarkdownContent";
import SettingsView from "./components/SettingsView";
import EngagementViewPanel from "./components/EngagementView";
import EmployeeWorkbenchPanel from "./components/EmployeeWorkbench";
import { ShellNav as ShellNavComponent, TopBar as TopBarComponent, SettingsStrip as SettingsStripComponent, PipelineBoard as PipelineBoardComponent } from "./components/Layout";

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
const renderMarkdown = (content: string, className?: string) => <MarkdownContent content={content} className={className} />;

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

// 中文说明：函数「SettingsView」负责完成该界面的状态处理、交互逻辑或数据转换。
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
        <PipelineBoardComponent run={run} running={running} onNew={onNew} onStep={onStep} onCancel={onCancel} onRerun={onRerun} onOpenArtifacts={onOpenArtifacts} />
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
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
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
      <ShellNavComponent
        activeView={activeView}
        onViewChange={setActiveView}
        closing={closing}
        shutdownComplete={shutdownComplete}
        onShutdown={handleShutdown}
      />
      <main className="main">
        <TopBarComponent
          activeView={activeView}
          status={status}
          running={running}
          onRun={() => void handleRun()}
        />
        {projectMessage && (
          <div className="project-message-banner" role="status">
            <CircleDot size={17} />
            <span>{projectMessage}</span>
            <button type="button" aria-label="关闭提示" title="关闭提示" onClick={() => setProjectMessage(null)}>×</button>
          </div>
        )}
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
        {activeView === "stocks" && <StockAnalysisViewPanel />}
        {activeView === "editing" && <EditingQueueView outputs={outputs} seed={seed} />}
        {activeView === "engagement" && <EngagementViewPanel agents={agents} />}
        {activeView === "settings" && <SettingsView status={status} currentRun={run} onProjectMessage={setProjectMessage} viralAnalysis={viralAnalysis} onViralAnalysisChange={setViralAnalysis} systemStatusSnapshot={systemStatusSnapshot} onSystemStatusSnapshotChange={setSystemStatusSnapshot} onImport={(imported) => { importedRunRef.current = imported.id; setRun(imported); setSelectedTopicTitle(imported.selected_topic_title ?? null); setAgentOutputs(Object.fromEntries((imported.standalone_outputs ?? []).map((output) => [output.agent_id, output]))); }} onBackendStateChange={() => refreshBackendData()} />}
        {employeeIdFromView(activeView) && agents.find((agent) => agent.id === employeeIdFromView(activeView)) && (
            <EmployeeWorkbenchPanel
            agent={agents.find((agent) => agent.id === employeeIdFromView(activeView))!}
            seed={seed}
            viralAnalysis={viralAnalysis}
            onRun={(prompt: string, settings: Record<string, unknown>) => void handleSingleAgent(employeeIdFromView(activeView)!, prompt, settings)}
            busy={agentTaskStatuses[employeeIdFromView(activeView)!] === "running"}
            taskStatus={agentTaskStatuses[employeeIdFromView(activeView)!] ?? "idle"}
            error={agentErrors[employeeIdFromView(activeView)!] ?? null}
            output={agentOutputs[employeeIdFromView(activeView)!] ?? null}
            logs={agentLogs[employeeIdFromView(activeView)!] ?? []}
          />
        )}
        <SettingsStripComponent status={status} collapsed={settingsStripCollapsed} onToggle={() => setSettingsStripCollapsed((value) => !value)} />
      </main>
    </div>
  );
}
