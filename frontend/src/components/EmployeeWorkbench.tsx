import { useEffect, useState } from "react";
import { AlertCircle, Bot, Copy, Loader2, Play } from "lucide-react";
import MarkdownContent from "./MarkdownContent";
import { navItems, roleIcons } from "../data";
import type { Agent, AgentOutput, AgentTaskLog, TopicSeed, ViralAnalysisConfig } from "../types";

type AgentTaskStatus = "idle" | "running" | "completed" | "failed";
type ViewId = (typeof navItems)[number]["id"];
const agentTaskStatusText: Record<AgentTaskStatus, string> = { idle: "待调用", running: "执行中", completed: "已完成", failed: "执行失败" };
// These are the concrete employee descriptions used by the original console.
const viewMeta: Record<string, { title: string; subtitle: string }> = {
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
function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }
function readSaved<T>(key: string, fallback: T): T { try { const value = window.localStorage.getItem(key); return value ? JSON.parse(value) as T : fallback; } catch { return fallback; } }

// 中文说明：函数「EmployeeWorkbench」负责完成该界面的状态处理、交互逻辑或数据转换。
export default function EmployeeWorkbench({
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
  const [logClearCutoff, setLogClearCutoff] = useState<number | null>(null);
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
    setLogClearCutoff(null);
  }, [agent.id]);
  useEffect(() => { window.localStorage.setItem(`signalforge.employee.${agent.id}.form`, JSON.stringify({ prompt, videoFormat, editingRequirements, outputDir, timeoutSeconds })); }, [agent.id, prompt, videoFormat, editingRequirements, outputDir, timeoutSeconds]);
  const visibleLogs = logClearCutoff === null
    ? logs
    : logs.filter((entry) => Date.parse(entry.timestamp) > logClearCutoff);

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
            <div className="panel-heading tight"><div><h2>本员工日志</h2><p>仅清空当前页面显示，不会删除后端日志。</p></div><button className="ghost-button compact clear-log-button" type="button" onClick={() => setLogClearCutoff(Date.now())} disabled={!visibleLogs.length}>清空日志</button></div>
            {visibleLogs.length ? <div className="employee-log-list">{visibleLogs.slice().reverse().map((entry, index) => <div className="run-log-entry" key={`${entry.timestamp}-${index}`}><time>{new Date(entry.timestamp).toLocaleTimeString()}</time><span>{entry.message}</span></div>)}</div> : <small>暂无独立任务日志。</small>}
          </section>
        </div>
      </div>
    </div>
  );
}
