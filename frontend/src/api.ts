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

export function fetchStatus() {
  return request<ApiStatus>("/api/status");
}

export function fetchTimeoutSettings() {
  return request<TimeoutSettings>("/api/settings/timeouts");
}

export function updateTimeoutSettings(payload: TimeoutSettings) {
  return request<TimeoutSettings>("/api/settings/timeouts", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function fetchAgents() {
  return request<Agent[]>("/api/agents");
}

export function fetchOutputDirectorySettings() {
  return request<OutputDirectorySettings>("/api/settings/output-directories");
}

export function updateOutputDirectorySettings(payload: OutputDirectorySettings) {
  return request<OutputDirectorySettings>("/api/settings/output-directories", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function selectDirectory() {
  return request<{ path: string | null }>("/api/local/select-directory");
}

export function openArtifactsFolder(runId?: string | null) {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return request<{ path: string }>(`/api/local/open-artifacts${query}`);
}

export function fetchEnvSettings() {
  return request<EnvSettings>("/api/settings/env");
}

export function updateEnvSettings(payload: Record<string, string | number | null>) {
  return request<EnvSettings>("/api/settings/env", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function runAgent(agentId: string, payload: { prompt?: string; settings?: Record<string, unknown>; timeout_seconds?: number; project_run_id?: string | null }) {
  return request<AgentOutput>(`/api/agents/${agentId}/run`, {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId, ...payload })
  });
}

export function fetchAgentLogs(agentId: string) {
  return request<AgentTaskLog[]>(`/api/agents/${agentId}/logs`);
}

export function runHotVideoWorkflow(seed: TopicSeed, execution_mode: "auto" | "step" | "manual" = "auto", viral_analysis?: ViralAnalysisConfig) {
  return request<WorkflowRun>("/api/workflows/hot-video", {
    method: "POST",
    body: JSON.stringify({ seed, execution_mode, viral_analysis })
  });
}

export function fetchWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}`);
}

export function fetchWorkflows() {
  return request<WorkflowRun[]>("/api/workflows");
}

export function resumeWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/resume`, { method: "POST" });
}

export function stepWorkflow(runId: string, selected_topic_title?: string | null, stage?: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/step`, {
    method: "POST",
    body: JSON.stringify({ selected_topic_title: selected_topic_title ?? null, stage: stage ?? null })
  });
}

export function cancelWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/cancel`, { method: "POST" });
}

export function scoutTopics(seed: TopicSeed) {
  return request<Topic[]>("/api/topics/scout", {
    method: "POST",
    body: JSON.stringify(seed)
  });
}

export function generateScript(payload: {
  topic: string;
  angle: string;
  duration_seconds: number;
  audience: string;
}) {
  return request<AgentOutput>("/api/scripts/generate", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function analyzeStocks(payload: { stocks: string; days?: number; include_news?: boolean }) {
  return request<StockAnalysisResult>("/api/stocks/analyze", {
    method: "POST",
    body: JSON.stringify({ days: 120, include_news: true, ...payload })
  });
}

export function fetchMoneyPrinterTurboStatus() {
  return request<MoneyPrinterTurboStatus>("/api/video/moneyprinterturbo/status");
}

export function runMoneyPrinterTurbo(subject: string, extra_args: string[] = []) {
  return request<MoneyPrinterTurboRunResult>("/api/video/moneyprinterturbo/run", {
    method: "POST",
    body: JSON.stringify({ subject, extra_args })
  });
}

export function fetchSystemStatus() {
  return request<SystemStatus>("/local-control/status");
}

export function startBackend() {
  return request<ControlResult>("/local-control/backend/start", { method: "POST" });
}

export function stopBackend() {
  return request<ControlResult>("/local-control/backend/stop", { method: "POST" });
}

export function restartBackend() {
  return request<ControlResult>("/local-control/backend/restart", { method: "POST" });
}

export function stopFrontend() {
  return request<ControlResult>("/local-control/frontend/stop", { method: "POST" });
}

export function shutdownAll() {
  return request<ControlResult>("/local-control/shutdown", { method: "POST" });
}

export async function exportWorkflow(runId: string) {
  const response = await fetch(`/api/workflows/${runId}/export`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function importWorkflow(file: File) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/workflows/import", { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<WorkflowRun>;
}
