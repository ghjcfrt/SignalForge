import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Archive,
  Bot,
  CheckCircle2,
  CircleDot,
  ChartNoAxesCombined,
  Copy,
  Cpu,
  ExternalLink,
  FileText,
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
  Video,
  Wand2
} from "lucide-react";
import {
  fetchAgents,
  fetchWorkflow,
  fetchWorkflows,
  cancelWorkflow,
  analyzeStocks,
  fetchMoneyPrinterTurboStatus,
  fetchStatus,
  fetchSystemStatus,
  generateScript,
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
} from "./api";
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
} from "./types";

type ViewId = (typeof navItems)[number]["id"];

const defaultSeed: TopicSeed = {
  domain: "AI 圈",
  brief: "近期 AI 产品、模型、创业工具或内容生产热点",
  audience: "关注 AI 工具的一线创作者和创业者",
  duration_seconds: 110
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

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

// A stale browser snapshot can outlive the backend filter. Keep collection
// diagnostics out of the visible candidate cards until the server refreshes.
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

function readSavedView(): ViewId {
  const saved = readSaved<string>("signalforge.activeView", "overview");
  return navItems.some((item) => item.id === saved) ? saved as ViewId : "overview";
}

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
    subtitle: "给赵爽一个方向，快速形成可选题池。"
  },
  stocks: {
    title: "股票分析",
    subtitle: "财经、股票和股票新闻统一走 Stock Analysis Skill。"
  },
  scripts: {
    title: "脚本工坊",
    subtitle: "把热点角度变成 90-120 秒短视频口播脚本。"
  },
  editing: {
    title: "剪辑队列",
    subtitle: "查看小李生成的画幅、配音、字幕、素材和导出方案。"
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
  agent_viral_analyst: { title: "爆款分析师", subtitle: "独立制定传播角度、结构和表达规则。" },
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

function employeeIdFromView(view: ViewId): string | null {
  return view.startsWith("agent_") ? view.slice("agent_".length) : null;
}

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
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">热</div>
        <div>
          <strong>热讯工坊</strong>
          <span>AI 一人公司</span>
        </div>
      </div>

      <nav className="nav-list" aria-label="主导航">
        {navItems.map((item, index) => {
          const Icon = item.icon;
          return (
            <div key={item.id}>
              {index === 1 && <div className="nav-section-label">流水线员工</div>}
              {index === pipeline.length + 1 && <div className="nav-section-label">其他员工</div>}
              <button
                className={cn("nav-item", activeView === item.id && "active")}
                onClick={() => onViewChange(item.id)}
                type="button"
                aria-current={activeView === item.id ? "page" : undefined}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            </div>
          );
        })}
      </nav>

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

  return (
    <header className="topbar">
      <div>
        <h1>{meta.title}</h1>
        <p>{meta.subtitle}</p>
      </div>
      <div className="topbar-actions">
        <div className={cn("api-pill", status?.mode === "live" ? "ok" : "warn")} title={status?.diagnostic ?? undefined}>
          {status?.mode === "live" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{status ? statusText[status.mode] : "检测中"}</span>
        </div>
        <button className="primary-button" onClick={onRun} disabled={running}>
          {running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
          <span>{running ? "运行中" : "运行工作流"}</span>
        </button>
      </div>
    </header>
  );
}

function PipelineBoard({ run, running, onNew, onStep, onCancel, onRerun }: { run: WorkflowRun | null; running: boolean; onNew: () => void; onStep: () => void; onCancel: () => void; onRerun: (stage: string) => void }) {
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
            <span className={cn("run-state", (running || run?.status === "running") && "running", run?.status === "completed" && "done")}>
              {running ? "执行中" : run?.status === "paused" ? "已暂停" : run?.status === "queued" ? "待调度" : run?.status === "failed" ? "执行失败" : run?.status === "completed" ? "已完成" : "待开始"}
            </span>
            <button className="ghost-button compact" onClick={onNew} disabled={running} type="button">
              <Plus size={15} />
              <span>新任务</span>
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
                <span>{stage.owner}</span>
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

function SeedPanel({
  seed,
  onChange,
  onScript,
  scriptBusy
}: {
  seed: TopicSeed;
  onChange: (seed: TopicSeed) => void;
  onScript: () => void;
  scriptBusy: boolean;
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
      <div className="settings-handoff">
        <ChartNoAxesCombined size={16} />
        <span>爆款分析师的开关、数据来源和分析依据已统一到左侧“爆款分析师”页面。</span>
      </div>
      <button className="ghost-button" onClick={onScript} disabled={scriptBusy}>
        {scriptBusy ? <Loader2 className="spin" size={17} /> : <Wand2 size={17} />}
        <span>{scriptBusy ? "生成中" : "只生成脚本"}</span>
      </button>
    </section>
  );
}

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
                  <strong>{agent.name}</strong>
                  <span>{agent.title}</span>
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

function TopicList({ run, topics, selectable, selectedTitle, onSelect }: { run?: WorkflowRun | null; topics?: Topic[]; selectable?: boolean; selectedTitle?: string | null; onSelect?: (title: string | null) => void }) {
  const items = (topics ?? run?.topics ?? []).filter((topic) => !isDiagnosticTopic(topic));
  return (
    <section className="panel topics-panel">
      <div className="panel-heading tight">
        <div>
          <h2>热点候选</h2>
          <p>由赵爽初筛，星辰负责判断传播结构。不勾选则默认第一个。</p>
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

function OutputList({ outputs }: { outputs: AgentOutput[] }) {
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
              <span>{output.agent_name}</span>
              <strong>{output.title}</strong>
              <small>{output.artifact_path}</small>
            </summary>
            <pre>{output.content}</pre>
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

function SettingsStrip({ status }: { status: ApiStatus | null }) {
  return (
    <section className="settings-strip">
      <div>
        <span>Key Path</span>
        <strong>{status?.key_preview ?? "未配置"}</strong>
      </div>
      <div>
        <span>Base URL</span>
        <strong>{status?.base_url ?? "https://api.openlux.ai/v1"}</strong>
      </div>
      <div>
        <span>Model</span>
        <strong>{status?.model ?? "中转站自动选择"}</strong>
      </div>
      <div>
        <span>AI Health</span>
        <strong>{status?.model_available ? "模型可用" : status?.diagnostic ?? "检查中"}</strong>
      </div>
    </section>
  );
}

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
            <h2>赵爽的热点雷达</h2>
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

function ScriptStudioView({
  seed,
  onChange,
  onScript,
  scriptBusy,
  outputs
}: {
  seed: TopicSeed;
  onChange: (seed: TopicSeed) => void;
  onScript: () => void;
  scriptBusy: boolean;
  outputs: AgentOutput[];
}) {
  const scriptOutputs = outputs.filter((output) => output.agent_id === "copywriter");

  return (
    <div className="studio-grid">
      <SeedPanel
        seed={seed}
        onChange={onChange}
        onScript={onScript}
        scriptBusy={scriptBusy}
      />
      <OutputList outputs={scriptOutputs} />
    </div>
  );
}

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
            <p>小李的专属剪辑能力，基于 MoneyPrinterTurbo。</p>
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
            <div className={cn("mpt-result", mptResult.status === "completed" && "done")}>
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
            <p>小李负责剪辑计划，尤道理负责发布策略；完整跑一次工作流后会出现队列。</p>
          </div>
        </div>
        <div className="queue-grid">
          {editingOutputs.map((output) => (
            <article className="queue-card" key={`${output.agent_id}-${output.created_at}`}>
              <div className="queue-icon">{output.agent_id === "video_editor" ? <Video size={18} /> : <Archive size={18} />}</div>
              <div>
                <span>{output.agent_name}</span>
                <h3>{output.title}</h3>
                <p>{output.content.split("\n").find((line) => line.startsWith("- ")) ?? "已生成可执行方案。"}</p>
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
                <span>{agent.name}</span>
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

function EmployeeWorkbench({
  agent,
  seed,
  viralAnalysis,
  onSeedChange,
  onViralAnalysisChange,
  onRun,
  busy,
  output
}: {
  agent: Agent;
  seed: TopicSeed;
  viralAnalysis: ViralAnalysisConfig;
  onSeedChange: (seed: TopicSeed) => void;
  onViralAnalysisChange: (config: ViralAnalysisConfig) => void;
  onRun: (prompt: string, settings: Record<string, unknown>) => void;
  busy: boolean;
  output: AgentOutput | null;
}) {
  const [prompt, setPrompt] = useState("");
  const Icon = roleIcons[agent.id] ?? Bot;
  const isViral = agent.id === "viral_analyst";
  const isWriter = agent.id === "copywriter";
  const isHotspot = agent.id === "hotspot_monitor";

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
    });
  }

  return (
    <div className={cn("employee-workbench", isViral && "viral-workbench")}>
      <section className="panel employee-hero">
        <div className="stage-head">
          <div className="stage-icon"><Icon size={20} /></div>
          <span>{agent.name} · {agent.title}</span>
        </div>
        <h2>{agent.title}独立工作台</h2>
        <p>{agent.role}</p>
      </section>
      <div className="employee-work-grid">
        <section className="panel employee-settings">
          <div className="panel-heading tight"><div><h2>调用设置</h2><p>只调用当前员工，不启动整条流水线。</p></div></div>
          {isHotspot && <>
            <label><span>领域</span><input value={seed.domain} onChange={(event) => onSeedChange({ ...seed, domain: event.target.value })} /></label>
            <label><span>受众</span><input value={seed.audience} onChange={(event) => onSeedChange({ ...seed, audience: event.target.value })} /></label>
          </>}
          {isWriter && <>
            <label><span>主题</span><textarea value={seed.brief} onChange={(event) => onSeedChange({ ...seed, brief: event.target.value })} /></label>
            <label><span>时长（秒）</span><input type="number" min={30} max={240} value={seed.duration_seconds} onChange={(event) => onSeedChange({ ...seed, duration_seconds: Number(event.target.value) })} /></label>
          </>}
          {agent.id === "video_editor" && <>
            <label><span>视频画幅</span><select className="workbench-select" defaultValue="vertical"><option value="vertical">竖版 1080×1920</option><option value="horizontal">横版 1920×1080</option></select></label>
            <label><span>剪辑要求</span><textarea placeholder="例如：突出开场钩子，字幕每 12-16 字断行" /></label>
          </>}
          {agent.id === "operator" && <>
            <label><span>发布平台</span><select className="workbench-select" defaultValue="douyin"><option value="douyin">抖音</option><option value="xiaohongshu">小红书</option><option value="bilibili">B 站</option><option value="wechat">视频号</option></select></label>
            <label><span>运营目标</span><input defaultValue="提升完播率、收藏率和评论质量" /></label>
          </>}
          {agent.id === "product_manager" && <label><span>分析类型</span><select className="workbench-select" defaultValue="需求拆解"><option>需求拆解</option><option>竞品分析</option><option>产品路线图</option></select></label>}
          {agent.id === "programmer" && <label><span>技术栈 / 输出形式</span><input defaultValue="Python、FastAPI、React；输出实施方案" /></label>}
          {isViral && <>
            <label className="switch-line switch-control">
              <input type="checkbox" checked={viralAnalysis.enabled} onChange={(event) => onViralAnalysisChange({ ...viralAnalysis, enabled: event.target.checked })} />
              <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
              <span className="switch-copy"><strong>{viralAnalysis.enabled ? "已启用爆款分析师" : "已关闭爆款分析师"}</strong><small>{viralAnalysis.enabled ? "流水线会执行这一阶段" : "流水线会跳过这一阶段"}</small></span>
            </label>
            <div className="segmented-control"><button className={cn("segment-button", viralAnalysis.source === "socialdatax" && "selected")} onClick={() => onViralAnalysisChange({ ...viralAnalysis, source: "socialdatax" })} type="button">SocialDataX</button><button className={cn("segment-button", viralAnalysis.source === "manual" && "selected")} onClick={() => onViralAnalysisChange({ ...viralAnalysis, source: "manual" })} type="button">手写分析</button></div>
            <small className="field-hint">此处设置会同步到总览工作流；SocialDataX 只用于爆款样本分析，不是热点新闻源。</small>
            {viralAnalysis.source === "manual" && <textarea className="manual-analysis-input" value={viralAnalysis.manual_content} onChange={(event) => onViralAnalysisChange({ ...viralAnalysis, manual_content: event.target.value })} placeholder="填写具体爆款样本、数据或你的分析结论；不要粘贴角色提示词" />}
          </>}
          {agent.id === "stock_assistant" && <label><span>股票代码或名称</span><input value={seed.brief} onChange={(event) => onSeedChange({ ...seed, brief: event.target.value })} placeholder="600519, TSLA" /></label>}
          <label><span>本次任务</span><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={isHotspot ? "例如：找今天影响普通创作者的 AI 行业热点" : "描述这次要让员工完成什么"} /></label>
          <button className="primary-button" type="button" onClick={submit} disabled={busy}>{busy ? <Loader2 className="spin" size={17} /> : <Play size={17} />}<span>{busy ? "执行中" : `调用${agent.title}`}</span></button>
        </section>
        <section className="panel employee-output">
          <div className="panel-heading tight"><div><h2>独立产物</h2><p>结果会保存到本次独立调用记录。</p></div></div>
          {output ? <><small>{output.artifact_path}</small><pre>{output.content}</pre></> : <div className="empty-state"><Copy size={20} /><span>还没有调用结果。</span></div>}
        </section>
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

function EngagementView({ agents }: { agents: Agent[] }) {
  const [comments, setComments] = useState(initialComments);
  const [selectedId, setSelectedId] = useState(initialComments[0].id);
  const [draft, setDraft] = useState("");
  const selected = comments.find((comment) => comment.id === selectedId) ?? comments[0];
  const fallbackNames: Record<string, string> = { healer: "周周", operator: "尤道理", product_manager: "方瓷" };
  const agentName = (id: string) => agents.find((agent) => agent.id === id)?.name ?? fallbackNames[id] ?? id;

  useEffect(() => {
    if (!selected) return;
    setDraft(selected.status === "已回复" ? "已完成回复，可继续编辑" : selected.category === "情绪支持" ? "听起来你最近承受了不少压力，谢谢你愿意把这份感受说出来。可以先从今天最困扰你的一个小片段开始，给自己一点喘息的空间；如果这种疲惫持续影响生活，也建议找专业咨询师聊聊。" : "感谢你的留言，我们会把这个问题记录下来并持续完善。你也可以告诉我们更具体的使用场景。 ");
  }, [selectedId, selected?.status, selected?.category]);

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
          <label className="reply-label"><span>负责员工</span><select value={selected.assignedAgentId} onChange={(event) => setComments((items) => items.map((item) => item.id === selected.id ? { ...item, assignedAgentId: event.target.value } : item))}>{agents.filter((agent) => ["healer", "operator", "product_manager"].includes(agent.id)).map((agent) => <option key={agent.id} value={agent.id}>{agent.name} · {agent.title}</option>)}</select></label>
          <label className="reply-label"><span>回复内容</span><textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={7} /></label>
          <div className="reply-footer"><span><MessageCircle size={15} /> 建议由 {agentName(selected.assignedAgentId)} 回复</span><button className="primary-button" type="button" onClick={sendReply} disabled={selected.status === "已回复" || !draft.trim()}>{selected.status === "已回复" ? "已提交" : "提交回复"}</button></div>
        </>}
      </section>
    </div>
  );
}

function StockAnalysisView() {
  const [stocks, setStocks] = useState("600519");
  const [result, setResult] = useState<StockAnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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
            <h2>林量 · Stock Analysis Skill</h2>
            <p>财经、股票和股票新闻请求默认调用此 Skill。支持 A 股、港股、美股。</p>
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
          <pre>{result.report}</pre>
          <p className="risk-note">{result.disclaimer}</p>
        </section>
      )}
    </div>
  );
}

type ControlAction = "backend-start" | "backend-stop" | "backend-restart" | "frontend-stop";

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
            <strong>端口空闲</strong>
            <span>没有检测到监听进程</span>
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

function SettingsView({ status, currentRun, onImport, onBackendStateChange }: { status: ApiStatus | null; currentRun: WorkflowRun | null; onImport: (run: WorkflowRun) => void; onBackendStateChange: () => void }) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [controlBusy, setControlBusy] = useState<ControlAction | null>(null);
  const [controlMessage, setControlMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [timeoutSettings, setTimeoutSettings] = useState<TimeoutSettings | null>(null);
  const [timeoutDraft, setTimeoutDraft] = useState<TimeoutSettings>(defaultTimeoutSettings);
  const [unlimitedTimeouts, setUnlimitedTimeouts] = useState({ news: false, model: false });
  const [timeoutBusy, setTimeoutBusy] = useState(false);
  const [timeoutMessage, setTimeoutMessage] = useState<string | null>(null);

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

  function updateTimeoutDraft(field: keyof TimeoutSettings, value: string) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setTimeoutDraft((current) => ({ ...current, [field]: Math.max(1, Math.floor(parsed)) }));
  }

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
    try { onImport(await importWorkflow(file)); setControlMessage("项目已导入"); }
    catch (err) { setControlMessage(err instanceof Error ? err.message : "导入失败"); }
  }

  async function refreshSystemStatus() {
    const next = await fetchSystemStatus();
    setSystemStatus(next);
    return next;
  }

  useEffect(() => {
    refreshSystemStatus().catch((err: Error) => setControlMessage(err.message));
    const timer = window.setInterval(() => {
      refreshSystemStatus().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

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

  return (
    <div className="single-view">
      <div className="settings-overview-grid">
      <section className="panel settings-panel runtime-settings-panel">
        <div className="panel-heading tight">
          <div>
            <h2>运行配置</h2>
            <p>仅显示已配置密钥的首尾字符，中间内容始终打码。</p>
          </div>
        </div>
        <div className="settings-list">
          <div>
            <KeyRound size={18} />
            <span>Key Path</span>
            <strong>{status?.key_preview ?? "未配置"}</strong>
          </div>
          <div>
            <ExternalLink size={18} />
            <span>Base URL</span>
            <strong>{status?.base_url ?? "https://api.openlux.ai/v1"}</strong>
          </div>
          <div>
            <Bot size={18} />
            <span>Model</span>
            <strong>{status?.model ?? "中转站自动选择"}</strong>
          </div>
          <div>
            <FileText size={18} />
            <span>AI Mode</span>
            <strong>{status ? statusText[status.mode] : "检测中"}</strong>
          </div>
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
      </div>
      <div className="settings-management-grid">
      <section className="panel settings-panel timeout-settings-panel">
        <div className="panel-heading tight">
          <div>
            <h2>热点扫描超时</h2>
            <p>控制公开来源抓取和模型整理的等待时间，0 表示不限时。</p>
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
      <SettingsStrip status={status} />
    </div>
  );
}

function OverviewView({
  run,
  running,
  seed,
  setSeed,
  handleScript,
  scriptBusy,
  agents,
  outputs,
  onNew,
  onStep,
  onCancel,
  onRerun,
  selectedTopicTitle,
  onSelectTopic
}: {
  run: WorkflowRun | null;
  running: boolean;
  seed: TopicSeed;
  setSeed: (seed: TopicSeed) => void;
  handleScript: () => void;
  scriptBusy: boolean;
  agents: Agent[];
  outputs: AgentOutput[];
  onNew: () => void;
  onStep: () => void;
  onCancel: () => void;
  onRerun: (stage: string) => void;
  selectedTopicTitle: string | null;
  onSelectTopic: (title: string | null) => void;
}) {
  return (
    <div className="content-grid">
      <div className="left-stack">
        <PipelineBoard run={run} running={running} onNew={onNew} onStep={onStep} onCancel={onCancel} onRerun={onRerun} />
        <TopicList run={run} selectable={run?.status === "paused" && run.stage_status?.hotspot_monitor === "completed" && run.stage_status?.viral_analyst !== "completed"} selectedTitle={selectedTopicTitle} onSelect={onSelectTopic} />
        <OutputList outputs={outputs} />
      </div>
      <div className="right-stack">
        <SeedPanel
          seed={seed}
          onChange={setSeed}
          onScript={handleScript}
          scriptBusy={scriptBusy}
        />
        <AgentRoster agents={agents} />
      </div>
    </div>
  );
}

export default function App() {
  const [activeView, setActiveView] = useState<ViewId>(readSavedView);
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [seed, setSeed] = useState<TopicSeed>(() => readSaved("signalforge.seed", defaultSeed));
  const [viralAnalysis, setViralAnalysis] = useState<ViralAnalysisConfig>(readViralAnalysis);
  const [run, setRun] = useState<WorkflowRun | null>(readSavedRun);
  const [selectedTopicTitle, setSelectedTopicTitle] = useState<string | null>(() => readSaved< string | null>("signalforge.selectedTopicTitle", null));
  const [radarTopics, setRadarTopics] = useState<Topic[]>([]);
  const [extraOutputs, setExtraOutputs] = useState<AgentOutput[]>([]);
  const [running, setRunning] = useState(false);
  const [scriptBusy, setScriptBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  const [shutdownComplete, setShutdownComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentOutputs, setAgentOutputs] = useState<Record<string, AgentOutput | null>>({});

  const outputs = useMemo(() => {
    return [...extraOutputs, ...(run?.outputs ?? [])];
  }, [extraOutputs, run]);

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
      if (items.length) setRun(items[0]);
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

  function showRunError(result: WorkflowRun, fallback: string) {
    if (result.status === "failed") {
      setError(formatWorkflowError(result, fallback));
    }
  }

  async function handleSingleAgent(agentId: string, prompt: string, settings: Record<string, unknown>) {
    setAgentBusy(true);
    setError(null);
    try {
      const output = await runAgent(agentId, { prompt, settings });
      setAgentOutputs((current) => ({ ...current, [agentId]: output }));
    } catch (err) {
      setError(err instanceof Error ? err.message : `${agentId} 执行失败`);
    } finally {
      setAgentBusy(false);
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

  async function handleScript() {
    setScriptBusy(true);
    setError(null);
    try {
      const output = await generateScript({
        topic: seed.brief,
        angle: seed.domain,
        duration_seconds: seed.duration_seconds,
        audience: seed.audience
      });
      setExtraOutputs((items) => [output, ...items]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "脚本生成失败");
    } finally {
      setScriptBusy(false);
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
          running={running || agentBusy}
          onRun={() => {
            const agentId = employeeIdFromView(activeView);
            if (agentId) {
              void handleSingleAgent(agentId, "", {
                topic: seed.brief,
                audience: seed.audience,
                duration_seconds: seed.duration_seconds,
                domain: seed.domain,
                source: viralAnalysis.source,
                manual_content: viralAnalysis.manual_content
              });
            } else if (activeView === "radar") {
              void handleRadarScan();
            } else {
              void handleRun();
            }
          }}
        />
        {error && (
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
            handleScript={handleScript}
            scriptBusy={scriptBusy}
            agents={agents}
            outputs={outputs}
            onNew={handleNewTask}
            onStep={handleStep}
            onCancel={handleCancel}
            onRerun={handleRerun}
            selectedTopicTitle={selectedTopicTitle}
            onSelectTopic={handleSelectTopic}
          />
        )}
        {activeView === "radar" && (
          <RadarView topics={radarTopics} seed={seed} onChange={setSeed} onRun={handleRadarScan} running={running} />
        )}
        {activeView === "stocks" && <StockAnalysisView />}
        {activeView === "scripts" && (
          <ScriptStudioView
            seed={seed}
            onChange={setSeed}
            onScript={handleScript}
            scriptBusy={scriptBusy}
            outputs={outputs}
          />
        )}
        {activeView === "editing" && <EditingQueueView outputs={outputs} seed={seed} />}
        {activeView === "engagement" && <EngagementView agents={agents} />}
        {activeView === "settings" && <SettingsView status={status} currentRun={run} onImport={setRun} onBackendStateChange={() => refreshBackendData()} />}
        {employeeIdFromView(activeView) && agents.find((agent) => agent.id === employeeIdFromView(activeView)) && (
          <EmployeeWorkbench
            agent={agents.find((agent) => agent.id === employeeIdFromView(activeView))!}
            seed={seed}
            viralAnalysis={viralAnalysis}
            onSeedChange={setSeed}
            onViralAnalysisChange={setViralAnalysis}
            onRun={(prompt, settings) => void handleSingleAgent(employeeIdFromView(activeView)!, prompt, settings)}
            busy={agentBusy}
            output={agentOutputs[employeeIdFromView(activeView)!] ?? null}
          />
        )}
        {activeView !== "settings" && <SettingsStrip status={status} />}
      </main>
    </div>
  );
}
