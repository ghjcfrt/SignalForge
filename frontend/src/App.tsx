import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Archive,
  Bot,
  CheckCircle2,
  CircleDot,
  Copy,
  Cpu,
  ExternalLink,
  FileText,
  KeyRound,
  Loader2,
  Power,
  Play,
  RefreshCcw,
  RotateCcw,
  Search,
  Server,
  Sparkles,
  Square,
  Video,
  Wand2
} from "lucide-react";
import {
  fetchAgents,
  fetchMoneyPrinterTurboStatus,
  fetchStatus,
  fetchSystemStatus,
  generateScript,
  restartBackend,
  runHotVideoWorkflow,
  runMoneyPrinterTurbo,
  shutdownAll,
  startBackend,
  stopBackend,
  stopFrontend
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
} from "./types";

type ViewId = (typeof navItems)[number]["id"];

const defaultSeed: TopicSeed = {
  domain: "AI 圈",
  brief: "近期 AI 产品、模型、创业工具或内容生产热点",
  audience: "关注 AI 工具的一线创作者和创业者",
  duration_seconds: 110
};

const statusText = {
  live: "实时 AI",
  "local-template": "本地模板"
};

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
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
  scripts: {
    title: "脚本工坊",
    subtitle: "把热点角度变成 90-120 秒短视频口播脚本。"
  },
  editing: {
    title: "剪辑队列",
    subtitle: "查看小李生成的画幅、配音、字幕、素材和导出方案。"
  },
  agents: {
    title: "员工",
    subtitle: "管理每个 Agent 的职责、技能和独立工作区。"
  },
  settings: {
    title: "设置",
    subtitle: "检查模型、密钥变量、Base URL 和本地工作区约定。"
  }
};

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
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              className={cn("nav-item", activeView === item.id && "active")}
              key={item.id}
              onClick={() => onViewChange(item.id)}
              type="button"
              aria-current={activeView === item.id ? "page" : undefined}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="boss-card">
        <span>老板模式</span>
        <strong>你负责决策</strong>
        <p>AI 员工负责收集、分析、撰写、剪辑和运营产物。</p>
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
        <div className={cn("api-pill", status?.has_key ? "ok" : "warn")}>
          {status?.has_key ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
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

function PipelineBoard({ run, running }: { run: WorkflowRun | null; running: boolean }) {
  const completedIds = new Set(run?.outputs.map((output) => output.agent_id) ?? []);

  return (
    <section className="panel pipeline-panel">
      <div className="panel-heading">
        <div>
          <h2>内容生产流水线</h2>
          <p>热点监控员选题 -&gt; 文案助手写脚本 -&gt; 剪辑员生成成片方案。</p>
        </div>
        <span className={cn("run-state", run?.status === "completed" && "done")}>
          {running ? "Running" : run?.status ?? "Ready"}
        </span>
      </div>

      <div className="pipeline-grid">
        {pipeline.map((stage, index) => {
          const Icon = roleIcons[stage.agentId] ?? Bot;
          const done = completedIds.has(stage.agentId);
          const active = running && index === 0;
          return (
            <article className={cn("stage-card", done && "done", active && "active")} key={stage.agentId}>
              <div className="stage-head">
                <div className="stage-icon">
                  <Icon size={18} />
                </div>
                <span>{stage.owner}</span>
              </div>
              <h3>{stage.title}</h3>
              <strong>{stage.action}</strong>
              <p>{stage.description}</p>
              <div className="stage-foot">
                {done ? <CheckCircle2 size={16} /> : <CircleDot size={16} />}
                <span>{done ? "已产出" : "待调度"}</span>
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
          <p>给热点监控员和文案助手的本轮方向。</p>
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
      <button className="ghost-button" onClick={onScript} disabled={scriptBusy}>
        {scriptBusy ? <Loader2 className="spin" size={17} /> : <Wand2 size={17} />}
        <span>{scriptBusy ? "生成中" : "只生成脚本"}</span>
      </button>
    </section>
  );
}

function AgentRoster({ agents }: { agents: Agent[] }) {
  return (
    <section className="panel roster-panel">
      <div className="panel-heading tight">
        <div>
          <h2>AI 员工</h2>
          <p>每个员工拥有独立 Workspace。</p>
        </div>
      </div>
      <div className="roster-list">
        {agents.map((agent) => {
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
              <span className="agent-dot" aria-label={agent.status} />
            </article>
          );
        })}
      </div>
    </section>
  );
}

function TopicList({ run }: { run: WorkflowRun | null }) {
  return (
    <section className="panel topics-panel">
      <div className="panel-heading tight">
        <div>
          <h2>热点候选</h2>
          <p>由赵爽初筛，星辰负责判断传播结构。</p>
        </div>
      </div>
      <div className="topic-list">
        {(run?.topics ?? []).map((topic) => (
          <article className="topic-card" key={topic.title}>
            <div className="heat">
              <Sparkles size={15} />
              <span>{topic.heat}</span>
            </div>
            <h3>{topic.title}</h3>
            <p>{topic.angle}</p>
            <small>{topic.source_hint}</small>
          </article>
        ))}
        {!run?.topics?.length && (
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
          <p>每个 Agent 的结果都会写入本地工作区。</p>
        </div>
      </div>
      <div className="outputs-list">
        {outputs.map((output) => (
          <details className="output-item" key={`${output.agent_id}-${output.created_at}`} open={output.agent_id === "copywriter"}>
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
        <strong>OPENAI_API_KEY_YW_SF</strong>
      </div>
      <div>
        <span>Base URL</span>
        <strong>{status?.base_url ?? "https://api.wlai.vip/v1"}</strong>
      </div>
      <div>
        <span>Model</span>
        <strong>{status?.model ?? "gpt-4o-mini"}</strong>
      </div>
      <div>
        <span>Workspace</span>
        <strong>workspaces/agents/*</strong>
      </div>
    </section>
  );
}

function RadarView({ run, seed, onChange, onRun, running }: {
  run: WorkflowRun | null;
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
      <TopicList run={run} />
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
      <SeedPanel seed={seed} onChange={onChange} onScript={onScript} scriptBusy={scriptBusy} />
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

  return (
    <div className="single-view">
      <section className="panel mpt-panel">
        <div className="panel-heading tight">
          <div>
            <h2>MoneyPrinterTurbo</h2>
            <p>小李的专属剪辑 Skill，来源于 harry0703/MoneyPrinterTurbo 官方 Agent Skill。</p>
          </div>
          <span className={cn("run-state", mptStatus?.installed && "done")}>
            {mptStatus?.installed ? "installed" : "checking"}
          </span>
        </div>
        <div className="mpt-grid">
          <div>
            <span>上游出处</span>
            <strong>github.com/harry0703/MoneyPrinterTurbo</strong>
          </div>
          <div>
            <span>许可证</span>
            <strong>{mptStatus?.license ?? "MIT"}</strong>
          </div>
          <div>
            <span>Skill 路径</span>
            <strong>{mptStatus?.skill_dir ?? "workspaces/agents/video_editor/skills/moneyprinterturbo-video"}</strong>
          </div>
          <div>
            <span>默认命令</span>
            <strong>{mptStatus?.default_command ?? 'uv run --no-project --python 3.11 python mpt_agent.py --subject "<视频主题或脚本>"'}</strong>
          </div>
        </div>
        {!!mptStatus?.missing_env.length && (
          <div className="missing-env">
            <AlertCircle size={16} />
            <span>真实成片还需要：{mptStatus.missing_env.join("、")}</span>
          </div>
        )}
        <div className="mpt-actions">
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
          <p>每个 AI 员工都有清晰职责、技能来源和独立 Workspace。</p>
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
              <small className="agent-workspace">{agent.workspace}</small>
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

function SettingsView({ status, onBackendStateChange }: { status: ApiStatus | null; onBackendStateChange: () => void }) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [controlBusy, setControlBusy] = useState<ControlAction | null>(null);
  const [controlMessage, setControlMessage] = useState<string | null>(null);

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
      <section className="panel settings-panel">
        <div className="panel-heading tight">
          <div>
            <h2>运行配置</h2>
            <p>后端读取本地环境变量，不会把真实密钥写入前端。</p>
          </div>
        </div>
        <div className="settings-list">
          <div>
            <KeyRound size={18} />
            <span>Key Path</span>
            <strong>OPENAI_API_KEY_YW_SF</strong>
          </div>
          <div>
            <ExternalLink size={18} />
            <span>Base URL</span>
            <strong>{status?.base_url ?? "https://api.wlai.vip/v1"}</strong>
          </div>
          <div>
            <Bot size={18} />
            <span>Model</span>
            <strong>{status?.model ?? "gpt-4o-mini"}</strong>
          </div>
          <div>
            <FileText size={18} />
            <span>AI Mode</span>
            <strong>{status ? statusText[status.mode] : "检测中"}</strong>
          </div>
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
  outputs
}: {
  run: WorkflowRun | null;
  running: boolean;
  seed: TopicSeed;
  setSeed: (seed: TopicSeed) => void;
  handleScript: () => void;
  scriptBusy: boolean;
  agents: Agent[];
  outputs: AgentOutput[];
}) {
  return (
    <div className="content-grid">
      <div className="left-stack">
        <PipelineBoard run={run} running={running} />
        <TopicList run={run} />
        <OutputList outputs={outputs} />
      </div>
      <div className="right-stack">
        <SeedPanel seed={seed} onChange={setSeed} onScript={handleScript} scriptBusy={scriptBusy} />
        <AgentRoster agents={agents} />
      </div>
    </div>
  );
}

export default function App() {
  const [activeView, setActiveView] = useState<ViewId>("overview");
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [seed, setSeed] = useState<TopicSeed>(defaultSeed);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [extraOutputs, setExtraOutputs] = useState<AgentOutput[]>([]);
  const [running, setRunning] = useState(false);
  const [scriptBusy, setScriptBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  const [shutdownComplete, setShutdownComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
  }, []);

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      const result = await runHotVideoWorkflow(seed);
      setRun(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作流运行失败");
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
        <TopBar activeView={activeView} status={status} running={running} onRun={handleRun} />
        {error && (
          <div className="error-bar">
            <AlertCircle size={17} />
            <span>{error}</span>
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
          />
        )}
        {activeView === "radar" && (
          <RadarView run={run} seed={seed} onChange={setSeed} onRun={handleRun} running={running} />
        )}
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
        {activeView === "agents" && <AgentsView agents={agents} />}
        {activeView === "settings" && <SettingsView status={status} onBackendStateChange={() => refreshBackendData()} />}
        {activeView !== "settings" && <SettingsStrip status={status} />}
      </main>
    </div>
  );
}
