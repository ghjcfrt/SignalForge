import { Cpu, Loader2, Power, RotateCcw, Server, Square } from "lucide-react";
import type { ManagedServiceStatus } from "../types";

export type ControlAction = "backend-start" | "backend-stop" | "backend-restart" | "frontend-stop";

function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

// 函数「ServiceCard」负责完成该界面的状态处理、交互逻辑或数据转换。
export default function ServiceCard({ service, busyAction, onAction }: { service: ManagedServiceStatus; busyAction: ControlAction | null; onAction: (action: ControlAction) => void }) {
  const isBackend = service.name === "backend";
  const Icon = isBackend ? Server : Cpu;
  const stopAction = isBackend ? "backend-stop" : "frontend-stop";
  return <article className="service-card">
    <div className="service-head"><div className="service-title"><div className="stage-icon"><Icon size={18} /></div><div><strong>{isBackend ? "后端服务" : "前端服务"}</strong><span>{service.url}</span></div></div><span className={cn("service-status", service.running && "online", !service.running && service.port_occupied && "occupied")}>{service.running ? "运行中" : service.port_occupied ? "端口占用" : "已关闭"}</span></div>
    <div className="service-meta"><div><span>端口</span><strong>{service.port}</strong></div><div><span>进程</span><strong>{service.processes.length ? service.processes.map((item) => item.pid).join(" / ") : "无"}</strong></div></div>
    {/* 中段开始整理状态和派生数据，再交给后续渲染或提交逻辑。 */}
    <div className="service-process-list">{service.processes.length ? service.processes.map((process) => <div key={`${service.name}-${process.pid}`}><strong>PID {process.pid} · {process.name}</strong><span>{process.project_owned ? "本项目进程" : "非本项目进程"}</span></div>) : <div><strong>{service.running ? "当前服务进程" : "端口空闲"}</strong><span>{service.running ? "由当前控制台提供服务" : "没有检测到监听进程"}</span></div>}</div>
    <div className="service-actions">{isBackend && <><button className="ghost-button compact" onClick={() => onAction("backend-start")} disabled={!service.can_start || busyAction !== null}>{busyAction === "backend-start" ? <Loader2 className="spin" size={16} /> : <Power size={16} />}<span>启动后端</span></button><button className="ghost-button compact" onClick={() => onAction("backend-restart")} disabled={busyAction !== null}>{busyAction === "backend-restart" ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}<span>重启后端</span></button></>}<button className="danger-button compact" onClick={() => onAction(stopAction)} disabled={!service.can_stop || busyAction !== null}>{busyAction === stopAction ? <Loader2 className="spin" size={16} /> : <Square size={16} />}<span>{isBackend ? "关闭后端" : "关闭前端"}</span></button></div>
  </article>;
}
