import type {
  Agent,
  AgentOutput,
  ApiStatus,
  ControlResult,
  SystemStatus,
  MoneyPrinterTurboRunResult,
  MoneyPrinterTurboStatus,
  TopicSeed,
  WorkflowRun
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
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function fetchStatus() {
  return request<ApiStatus>("/api/status");
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
