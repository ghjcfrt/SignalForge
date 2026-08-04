import type {
  Agent,
  AgentOutput,
  ApiStatus,
  ControlResult,
  SystemStatus,
  MoneyPrinterTurboRunResult,
  MoneyPrinterTurboStatus,
  TopicSeed,
  Topic,
  WorkflowRun,
  TimeoutSettings
  ,StockAnalysisResult
} from "./types";

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

export function runHotVideoWorkflow(seed: TopicSeed) {
  return request<WorkflowRun>("/api/workflows/hot-video", {
    method: "POST",
    body: JSON.stringify({ seed })
  });
}

export function resumeWorkflow(runId: string) {
  return request<WorkflowRun>(`/api/workflows/${runId}/resume`, { method: "POST" });
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
