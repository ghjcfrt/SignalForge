/** 前端 API 请求封装与响应类型转换。 */

import type {
  Agent,
  AgentOutput,
  ApiStatus,
  ControlResult,
  SystemStatus,
  MoneyPrinterTurboRunResult,
  MoneyPrinterTurboStatus,
  TopicSeed,
  ViralAnalysisConfig,
  Topic,
  WorkflowRun,
  TimeoutSettings,
  EnvSettings
  ,StockAnalysisResult
  ,AgentTaskLog
} from "./types";
import type { OutputDirectorySettings } from "./types";

/** 统一发送 HTTP 请求，解析 JSON 响应并把错误转换为 Error。 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    },
    ...options
  });

  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try {
      const payload = JSON.parse(body) as { detail?: string };
      message = payload.detail || body;
    } catch {
      // 服务端返回非 JSON 时，保留可读的原始文本。
    }
    throw new Error(message || `请求失败：${response.status}`);
  }

  return response.json() as Promise<T>;
}

/** 读取模型连接状态。 */
export function fetchStatus() {
  return request<ApiStatus>("/api/status");
}

/** 读取工作流超时配置。 */
export function fetchTimeoutSettings() {
  return request<TimeoutSettings>("/api/settings/timeouts");
}

/** 保存工作流超时配置。 */
export function updateTimeoutSettings(payload: TimeoutSettings) {
  return request<TimeoutSettings>("/api/settings/timeouts", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

/** 读取员工列表。 */
export function fetchAgents() {
  return request<Agent[]>("/api/agents");
}

/** 读取产物输出目录配置。 */
export function fetchOutputDirectorySettings() {
  return request<OutputDirectorySettings>("/api/settings/output-directories");
}

/** 保存产物输出目录配置。 */
export function updateOutputDirectorySettings(payload: OutputDirectorySettings) {
  return request<OutputDirectorySettings>("/api/settings/output-directories", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

/** 打开原生目录选择器。 */
export function selectDirectory() {
  return request<{ path: string | null }>("/api/local/select-directory");
}

/** 打开产物目录。 */
export function openArtifactsFolder() {
  return request<{ path: string }>("/api/local/open-artifacts");
}

/** 读取脱敏后的环境变量配置。 */
export function fetchEnvSettings() {
  return request<EnvSettings>("/api/settings/env");
}

/** 保存可编辑的环境变量配置。 */
export function updateEnvSettings(payload: Record<string, string | number | null>) {
  return request<EnvSettings>("/api/settings/env", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

/** 独立调用指定员工并返回产物。 */
export function runAgent(agentId: string, payload: { prompt?: string; settings?: Record<string, unknown>; timeout_seconds?: number; project_run_id?: string | null }) {
  return request<AgentOutput>(`/api/agents/${agentId}/run`, {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId, ...payload })
  });
}

/** 读取指定员工的执行日志。 */
export function fetchAgentLogs(agentId: string) {
  return request<AgentTaskLog[]>(`/api/agents/${agentId}/logs`);
}

/** 创建并启动或暂停热点视频工作流。 */
export function runHotVideoWorkflow(seed: TopicSeed, execution_mode: "auto" | "step" | "manual" = "auto", viral_analysis?: ViralAnalysisConfig) {
  return request<WorkflowRun>("/api/workflows/hot-video", {
    method: "POST",
    body: JSON.stringify({ seed, execution_mode, viral_analysis })
  });
}

/** 读取单个工作流状态。 */
export function fetchWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}`);
}

/** 读取工作流列表。 */
export function fetchWorkflows() {
  return request<WorkflowRun[]>("/api/workflows");
}

/** 从检查点继续工作流。 */
export function resumeWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/resume`, { method: "POST" });
}

/** 执行工作流的下一阶段或指定重跑阶段。 */
export function stepWorkflow(runId: string, selected_topic_title?: string | null, stage?: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/step`, {
    method: "POST",
    body: JSON.stringify({ selected_topic_title: selected_topic_title ?? null, stage: stage ?? null })
  });
}

/** 取消工作流。 */
export function cancelWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/cancel`, { method: "POST" });
}

/** 只执行热点扫描并返回候选选题。 */
export function scoutTopics(seed: TopicSeed) {
  return request<Topic[]>("/api/topics/scout", {
    method: "POST",
    body: JSON.stringify(seed)
  });
}

/** 提交股票分析请求。 */
export function analyzeStocks(payload: { stocks: string; days?: number; include_news?: boolean }) {
  return request<StockAnalysisResult>("/api/stocks/analyze", {
    method: "POST",
    body: JSON.stringify({ days: 120, include_news: true, ...payload })
  });
}

/** 读取股票数据源健康状态。 */
export function fetchStockSourcesHealth() {
  return request<{ status: string; libraries: Record<string, string>; credentials: Record<string, string>; retry_limit: number; cache_ttl_seconds: number }>("/api/stocks/health");
}

/** 读取视频生成工具状态。 */
export function fetchMoneyPrinterTurboStatus() {
  return request<MoneyPrinterTurboStatus>("/api/video/moneyprinterturbo/status");
}

/** 启动一次视频生成任务。 */
export function runMoneyPrinterTurbo(subject: string, extra_args: string[] = []) {
  return request<MoneyPrinterTurboRunResult>("/api/video/moneyprinterturbo/run", {
    method: "POST",
    body: JSON.stringify({ subject, extra_args })
  });
}

/** 读取本地前后端进程状态。 */
export function fetchSystemStatus() {
  return request<SystemStatus>("/local-control/status");
}

/** 启动本地后端。 */
export function startBackend() {
  return request<ControlResult>("/local-control/backend/start", { method: "POST" });
}

/** 停止本地后端。 */
export function stopBackend() {
  return request<ControlResult>("/local-control/backend/stop", { method: "POST" });
}

/** 重启本地后端。 */
export function restartBackend() {
  return request<ControlResult>("/local-control/backend/restart", { method: "POST" });
}

/** 停止本地前端。 */
export function stopFrontend() {
  return request<ControlResult>("/local-control/frontend/stop", { method: "POST" });
}

/** 停止本地前后端。 */
export function shutdownAll() {
  return request<ControlResult>("/local-control/shutdown", { method: "POST" });
}

/** 导出工作流项目数据。 */
export async function exportWorkflow(runId: string) {
  const response = await fetch(`/api/workflows/${runId}/export`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

/** 上传并导入工作流项目数据。 */
export async function importWorkflow(file: File) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/workflows/import", { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<WorkflowRun>;
}
