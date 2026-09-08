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

// 中文说明：函数「request」负责统一发送前端 API 请求、解析响应并转换错误信息。
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
      // Keep non-JSON server responses readable.
    }
    throw new Error(message || `请求失败：${response.status}`);
  }

  return response.json() as Promise<T>;
}

// 中文说明：函数「fetchStatus」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchStatus() {
  return request<ApiStatus>("/api/status");
}

// 中文说明：函数「fetchTimeoutSettings」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchTimeoutSettings() {
  return request<TimeoutSettings>("/api/settings/timeouts");
}

// 中文说明：函数「updateTimeoutSettings」负责完成该界面的状态处理、交互逻辑或数据转换。
export function updateTimeoutSettings(payload: TimeoutSettings) {
  return request<TimeoutSettings>("/api/settings/timeouts", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

// 中文说明：函数「fetchAgents」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchAgents() {
  return request<Agent[]>("/api/agents");
}

// 中文说明：函数「fetchOutputDirectorySettings」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchOutputDirectorySettings() {
  return request<OutputDirectorySettings>("/api/settings/output-directories");
}

// 中文说明：函数「updateOutputDirectorySettings」负责完成该界面的状态处理、交互逻辑或数据转换。
export function updateOutputDirectorySettings(payload: OutputDirectorySettings) {
  return request<OutputDirectorySettings>("/api/settings/output-directories", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

// 中文说明：函数「selectDirectory」负责完成该界面的状态处理、交互逻辑或数据转换。
export function selectDirectory() {
  return request<{ path: string | null }>("/api/local/select-directory");
}

// 中文说明：函数「openArtifactsFolder」负责完成该界面的状态处理、交互逻辑或数据转换。
export function openArtifactsFolder() {
  return request<{ path: string }>("/api/local/open-artifacts");
}

// 中文说明：函数「fetchEnvSettings」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchEnvSettings() {
  return request<EnvSettings>("/api/settings/env");
}

// 中文说明：函数「updateEnvSettings」负责完成该界面的状态处理、交互逻辑或数据转换。
export function updateEnvSettings(payload: Record<string, string | number | null>) {
  return request<EnvSettings>("/api/settings/env", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

// 中文说明：函数「runAgent」负责完成该界面的状态处理、交互逻辑或数据转换。
export function runAgent(agentId: string, payload: { prompt?: string; settings?: Record<string, unknown>; timeout_seconds?: number; project_run_id?: string | null }) {
  return request<AgentOutput>(`/api/agents/${agentId}/run`, {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId, ...payload })
  });
}

// 中文说明：函数「fetchAgentLogs」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchAgentLogs(agentId: string) {
  return request<AgentTaskLog[]>(`/api/agents/${agentId}/logs`);
}

// 中文说明：函数「runHotVideoWorkflow」负责完成该界面的状态处理、交互逻辑或数据转换。
export function runHotVideoWorkflow(seed: TopicSeed, execution_mode: "auto" | "step" | "manual" = "auto", viral_analysis?: ViralAnalysisConfig) {
  return request<WorkflowRun>("/api/workflows/hot-video", {
    method: "POST",
    body: JSON.stringify({ seed, execution_mode, viral_analysis })
  });
}

// 中文说明：函数「fetchWorkflow」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}`);
}

// 中文说明：函数「fetchWorkflows」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchWorkflows() {
  return request<WorkflowRun[]>("/api/workflows");
}

// 中文说明：函数「resumeWorkflow」负责完成该界面的状态处理、交互逻辑或数据转换。
export function resumeWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/resume`, { method: "POST" });
}

// 中文说明：函数「stepWorkflow」负责完成该界面的状态处理、交互逻辑或数据转换。
export function stepWorkflow(runId: string, selected_topic_title?: string | null, stage?: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/step`, {
    method: "POST",
    body: JSON.stringify({ selected_topic_title: selected_topic_title ?? null, stage: stage ?? null })
  });
}

// 中文说明：函数「cancelWorkflow」负责完成该界面的状态处理、交互逻辑或数据转换。
export function cancelWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/cancel`, { method: "POST" });
}

// 中文说明：函数「scoutTopics」负责完成该界面的状态处理、交互逻辑或数据转换。
export function scoutTopics(seed: TopicSeed) {
  return request<Topic[]>("/api/topics/scout", {
    method: "POST",
    body: JSON.stringify(seed)
  });
}

// 中文说明：函数「analyzeStocks」负责完成该界面的状态处理、交互逻辑或数据转换。
export function analyzeStocks(payload: { stocks: string; days?: number; include_news?: boolean }) {
  return request<StockAnalysisResult>("/api/stocks/analyze", {
    method: "POST",
    body: JSON.stringify({ days: 120, include_news: true, ...payload })
  });
}

// 中文说明：函数「fetchStockSourcesHealth」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchStockSourcesHealth() {
  return request<{ status: string; libraries: Record<string, string>; credentials: Record<string, string>; retry_limit: number; cache_ttl_seconds: number }>("/api/stocks/health");
}

// 中文说明：函数「fetchMoneyPrinterTurboStatus」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchMoneyPrinterTurboStatus() {
  return request<MoneyPrinterTurboStatus>("/api/video/moneyprinterturbo/status");
}

// 中文说明：函数「runMoneyPrinterTurbo」负责完成该界面的状态处理、交互逻辑或数据转换。
export function runMoneyPrinterTurbo(subject: string, extra_args: string[] = []) {
  return request<MoneyPrinterTurboRunResult>("/api/video/moneyprinterturbo/run", {
    method: "POST",
    body: JSON.stringify({ subject, extra_args })
  });
}

// 中文说明：函数「fetchSystemStatus」负责完成该界面的状态处理、交互逻辑或数据转换。
export function fetchSystemStatus() {
  return request<SystemStatus>("/local-control/status");
}

// 中文说明：函数「startBackend」负责完成该界面的状态处理、交互逻辑或数据转换。
export function startBackend() {
  return request<ControlResult>("/local-control/backend/start", { method: "POST" });
}

// 中文说明：函数「stopBackend」负责完成该界面的状态处理、交互逻辑或数据转换。
export function stopBackend() {
  return request<ControlResult>("/local-control/backend/stop", { method: "POST" });
}

// 中文说明：函数「restartBackend」负责完成该界面的状态处理、交互逻辑或数据转换。
export function restartBackend() {
  return request<ControlResult>("/local-control/backend/restart", { method: "POST" });
}

// 中文说明：函数「stopFrontend」负责完成该界面的状态处理、交互逻辑或数据转换。
export function stopFrontend() {
  return request<ControlResult>("/local-control/frontend/stop", { method: "POST" });
}

// 中文说明：函数「shutdownAll」负责完成该界面的状态处理、交互逻辑或数据转换。
export function shutdownAll() {
  return request<ControlResult>("/local-control/shutdown", { method: "POST" });
}

// 中文说明：函数「exportWorkflow」负责请求服务端导出指定工作流的项目数据。
export async function exportWorkflow(runId: string) {
  const response = await fetch(`/api/workflows/${runId}/export`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

// 中文说明：函数「importWorkflow」负责上传项目文件并恢复服务端工作流记录。
export async function importWorkflow(file: File) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/workflows/import", { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<WorkflowRun>;
}
