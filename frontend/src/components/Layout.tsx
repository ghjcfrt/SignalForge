import { useEffect, useState } from "react";
import { AlertCircle, Bot, CheckCircle2, ChevronLeft, ChevronRight, CircleDot, FolderOpen, Loader2, Play, Plus, Power, Square } from "lucide-react";
import { navItems, pipeline, roleIcons } from "../data";
import type { Agent, AgentOutput, ApiStatus, WorkflowRun } from "../types";

export type ViewId = (typeof navItems)[number]["id"];
export const viewMeta: Record<string, { title: string; subtitle: string }> = {
  overview: { title: "总控制台", subtitle: "从老板指令到最终成片的统一调度台" },
  radar: { title: "热点雷达", subtitle: "抓取、筛选并核验公开热点" },
  stocks: { title: "股票分析", subtitle: "基于公开数据生成研究摘要" },
  editing: { title: "剪辑队列", subtitle: "查看剪辑与发布产物" },
  engagement: { title: "互动中心", subtitle: "处理评论与用户反馈" },
  settings: { title: "设置", subtitle: "配置运行时和员工能力" },
  agent_product_manager: { title: "产品经理", subtitle: "独立员工工作台" },
  agent_programmer: { title: "程序员", subtitle: "独立员工工作台" },
  agent_stock_assistant: { title: "股票助手", subtitle: "独立员工工作台" },
  agent_healer: { title: "自愈工程师", subtitle: "独立员工工作台" }
};

function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

export function ShellNav({ activeView, onViewChange, closing, shutdownComplete, onShutdown }: { activeView: ViewId; onViewChange: (view: ViewId) => void; closing: boolean; shutdownComplete: boolean; onShutdown: () => void }) {
  const moreViewIds = new Set(["agent_product_manager", "agent_programmer", "agent_stock_assistant", "agent_healer", "radar", "stocks", "editing", "engagement"]);
  const primaryItems = navItems.filter((item) => item.id !== "settings" && !moreViewIds.has(item.id));
  const moreItems = navItems.filter((item) => moreViewIds.has(item.id));
  const [moreOpen, setMoreOpen] = useState(() => moreViewIds.has(activeView));
  useEffect(() => { if (moreViewIds.has(activeView)) setMoreOpen(true); }, [activeView]);
  const renderNavItem = (item: (typeof navItems)[number], subItem = false) => { const Icon = item.icon; return <button className={cn("nav-item", subItem && "nav-sub-item", activeView === item.id && "active")} onClick={() => onViewChange(item.id)} type="button" aria-current={activeView === item.id ? "page" : undefined} key={item.id}><Icon size={subItem ? 17 : 18} /><span>{item.label}</span></button>; };
  return <aside className="sidebar">
    <div className="brand"><div className="brand-mark">热</div><div><strong>热讯工坊</strong><span>AI 一人公司</span></div></div>
    <div className="nav-scroll-area"><nav className="nav-list" aria-label="主导航">{primaryItems.filter((item) => item.id === "overview").map((item) => renderNavItem(item))}<div className="nav-section-label">独立工作台</div>{primaryItems.filter((item) => item.id !== "overview").map((item) => renderNavItem(item))}</nav><div className="nav-more-group"><details className="nav-collapsible" open={moreOpen} onToggle={(event) => setMoreOpen(event.currentTarget.open)}><summary className="nav-collapse-summary"><span>更多</span><ChevronRight size={15} aria-hidden="true" /></summary><div className="nav-collapsible-items">{moreItems.map((item) => renderNavItem(item, true))}</div></details></div></div>
    <div className="sidebar-settings"><div className="nav-divider" aria-hidden="true" />{renderNavItem(navItems.find((item) => item.id === "settings")!)}</div>
    <div className="boss-card"><span>实时 AI 工作台</span><strong>你负责方向与验收</strong><p>Agent 实时调用模型，协同完成收集、分析、写作、剪辑和运营。</p></div>
    <button className="shutdown-button" onClick={onShutdown} disabled={closing || shutdownComplete} type="button">{closing ? <Loader2 className="spin" size={17} /> : <Power size={17} />}<span>{closing ? "正在关闭" : shutdownComplete ? "服务已关闭" : "退出并关闭服务"}</span></button>
  </aside>;
}

export function TopBar({ activeView, status, running, onRun }: { activeView: ViewId; status: ApiStatus | null; running: boolean; onRun: () => void }) {
  const meta = viewMeta[activeView]; const isEmployeeView = activeView.startsWith("agent_"); const isConsoleView = activeView === "overview";
  return <header className="topbar"><div><h1>{isEmployeeView ? "独立工作台" : meta.title}</h1>{!isEmployeeView && <p>{meta.subtitle}</p>}</div><div className="topbar-actions"><div className={cn("api-pill", status?.mode === "live" ? "ok" : "warn")} title={status?.diagnostic ?? undefined}>{status?.mode === "live" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}<span>{status ? ({ live: "实时 AI", "local-template": "本地模板" } as Record<string, string>)[status.mode] : "检测中"}</span></div>{isConsoleView && <button className="primary-button" onClick={onRun} disabled={running}>{running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}<span>{running ? "运行中" : "运行工作流"}</span></button>}</div></header>;
}

export function SettingsStrip({ status, collapsed, onToggle }: { status: ApiStatus | null; collapsed: boolean; onToggle: () => void }) {
  return <section className={cn("settings-strip", collapsed && "collapsed")} aria-label="AI 运行状态">{!collapsed && <div className="settings-strip-content"><div><span>Key Path</span><strong>{status?.key_preview ?? "未配置"}</strong></div><div><span>Base URL</span><strong>{status?.base_url ?? "https://api.openlux.ai/v1"}</strong></div><div><span>Model</span><strong>{status?.model ?? "中转站自动选择"}</strong></div><div><span>AI Health</span><strong>{status?.model_available ? "模型可用" : status?.diagnostic ?? "检查中"}</strong></div></div>}<button className="settings-strip-toggle" type="button" onClick={onToggle} aria-label={collapsed ? "展开 AI 运行状态" : "收起 AI 运行状态"} title={collapsed ? "展开 AI 运行状态" : "收起 AI 运行状态"}>{collapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}</button></section>;
}

export function PipelineBoard({ run, running, onNew, onStep, onCancel, onRerun, onOpenArtifacts }: { run: WorkflowRun | null; running: boolean; onNew: () => void; onStep: () => void; onCancel: () => void; onRerun: (stage: string) => void; onOpenArtifacts: () => void }) {
  const completedIds = new Set(run?.outputs.map((output) => output.agent_id) ?? []); const stageStatus = run?.stage_status ?? {}; const statusLabels = { pending: "待调度", running: "执行中", completed: "已产出", failed: "失败" };
  return <section className="panel pipeline-panel"><div className="panel-heading"><div><h2>内容生产流水线</h2><p>热点监控员选题 -&gt; 爆款分析师定结构 -&gt; 文案助手写脚本 -&gt; 剪辑员成片。</p></div><div className="pipeline-actions"><span className={cn("run-state", (running || run?.status === "running" || run?.status === "queued") && "running", run?.status === "completed" && "done", run?.status === "failed" && "failed")}>{running ? "执行中" : run?.status === "paused" ? "已暂停" : run?.status === "queued" ? "待调度" : run?.status === "failed" ? "执行失败" : run?.status === "completed" ? "已完成" : "待开始"}</span><button className="ghost-button compact" onClick={onNew} disabled={running} type="button"><Plus size={15} /><span>新任务</span></button><button className="ghost-button compact" onClick={onOpenArtifacts} type="button" title="打开全部产物文件夹"><FolderOpen size={15} /><span>打开产物文件夹</span></button>{run && run.status !== "completed" && <button className="ghost-button compact" onClick={onStep} disabled={running} type="button">执行下一步</button>}{running && <button className="danger-button compact" onClick={onCancel} type="button"><Square size={15} /><span>停止任务</span></button>}</div></div>{run?.logs?.length ? <details className="run-logs"><summary>查看执行日志（{run.logs.length} 条）</summary><div className="run-log-list">{run.logs.slice().reverse().map((entry, index) => <div className={cn("run-log-entry", entry.level === "error" && "error")} key={`${entry.timestamp}-${index}`}><time>{new Date(entry.timestamp).toLocaleTimeString()}</time><span>{entry.stage ? `[${entry.stage}] ` : ""}{entry.message}</span>{entry.detail && <code>{entry.detail}</code>}</div>)}</div>{run.log_file && <small className="log-path">日志文件：{run.log_file}</small>}</details> : null}<div className="pipeline-grid">{pipeline.map((stage, index) => { const Icon = roleIcons[stage.agentId] ?? Bot; const state = stageStatus[stage.agentId] ?? (completedIds.has(stage.agentId) ? "completed" : "pending"); const done = state === "completed"; const active = state === "running" || (running && index === 0 && !run); return <article className={cn("stage-card", done && "done", active && "active", state === "failed" && "failed")} key={stage.agentId}><div className="stage-head"><div className="stage-icon"><Icon size={18} /></div>{run && !running && state !== "running" && <button className="ghost-button rerun-stage" type="button" onClick={() => onRerun(stage.agentId)}>重跑</button>}</div><h3>{stage.title}</h3><strong>{stage.action}</strong><p>{stage.description}</p><div className="stage-foot">{done ? <CheckCircle2 size={16} /> : <CircleDot size={16} />}<span>{statusLabels[state as keyof typeof statusLabels] ?? "待调度"}</span></div></article>; })}</div></section>;
}
