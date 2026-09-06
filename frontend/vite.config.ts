import { execFile, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const execFileAsync = promisify(execFile);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const workspaceRoot = path.resolve(__dirname, "..");
const backendPort = Number(process.env.BACKEND_PORT ?? 8017);
const frontendPort = Number(process.env.FRONTEND_PORT ?? 5173);
let systemStatusCache: { value: SystemStatus; expiresAt: number } | null = null;

type ManagedProcess = {
  pid: number;
  parent_pid: number | null;
  name: string;
  command_line: string;
  project_owned: boolean;
};

type ManagedServiceStatus = {
  name: "backend" | "frontend";
  running: boolean;
  port_occupied: boolean;
  port: number;
  url: string;
  processes: ManagedProcess[];
  can_start: boolean;
  can_stop: boolean;
};

type SystemStatus = {
  backend: ManagedServiceStatus;
  frontend: ManagedServiceStatus;
  workspace: string;
  generated_at: string;
};

function psString(value: string) {
  return `'${value.replace(/'/g, "''")}'`;
}

async function runPowerShell(script: string) {
  const { stdout } = await execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
    {
      cwd: workspaceRoot,
      maxBuffer: 1024 * 1024,
      windowsHide: true,
      timeout: 5000
    }
  );
  return stdout.trim();
}

// WMI queries are unusually slow on Windows and frequently time out while a
// reloading uvicorn process is spawning. netstat/tasklist provide the actual
// listener PID quickly, so the control panel never has to invent PID 0.
async function getNativeProcessSnapshot(port: number): Promise<ManagedProcess[]> {
  if (process.platform !== "win32") return [];
  const { stdout: netstat } = await execFileAsync("netstat.exe", ["-ano", "-p", "tcp"], {
    windowsHide: true, timeout: 3000, maxBuffer: 1024 * 1024
  });
  const pids = new Set<number>();
  for (const line of netstat.split(/\r?\n/)) {
    const fields = line.trim().split(/\s+/);
    if (fields.length < 5 || fields[0].toUpperCase() !== "TCP") continue;
    const pid = Number(fields[4]);
    if (fields[3].toUpperCase() === "LISTENING" && Number(fields[1].slice(fields[1].lastIndexOf(":") + 1)) === port && pid > 0) pids.add(pid);
  }
  if (!pids.size) return [];
  const { stdout: tasklist } = await execFileAsync("tasklist.exe", ["/FO", "CSV", "/NH"], {
    windowsHide: true, timeout: 3000, maxBuffer: 2 * 1024 * 1024
  });
  const names = new Map<number, string>();
  for (const line of tasklist.split(/\r?\n/)) {
    const match = line.match(/^"([^"]+)"\s*,\s*"(\d+)"/);
    if (match) names.set(Number(match[2]), match[1]);
  }
  return [...pids].map((pid) => ({
    pid, parent_pid: null, name: names.get(pid) ?? "unknown",
    command_line: names.get(pid) ?? "unknown", project_owned: false
  }));
}

function normalizeProcessList(raw: string): ManagedProcess[] {
  if (!raw) {
    return [];
  }
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [parsed];
}

async function getPortProcesses(port: number): Promise<ManagedProcess[]> {
  try {
    const native = await getNativeProcessSnapshot(port);
    if (process.platform === "win32") return native;
  } catch {
    // Use the richer WMI path below when native enumeration is unavailable.
  }
  const root = psString(workspaceRoot);
  const script = `
$portValue = ${port}
$root = ${root}
function Test-BackendCommand([string]$commandLine) {
  return ($commandLine -match '(?i)backend\.app\.main:app' -and $commandLine -match '(?i)(uvicorn(?:\.exe)?|python(?:\.exe)?)')
}
$pids = @(Get-NetTCPConnection -LocalPort $portValue -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' -and [int]$_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique)
$items = foreach ($pidValue in $pids) {
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue"
  if ($proc) {
    $cmd = [string]$proc.CommandLine
    [pscustomobject]@{
      pid = [int]$proc.ProcessId
      parent_pid = [int]$proc.ParentProcessId
      name = [System.IO.Path]::GetFileName([string]$proc.ExecutablePath)
      command_line = $cmd
      project_owned = $cmd.Contains($root) -or (Test-BackendCommand $cmd)
    }
  }
}
@($items) | ConvertTo-Json -Depth 4
`;
  try {
    return normalizeProcessList(await runPowerShell(script));
  } catch {
    // WMI can briefly lag while uvicorn is spawning/restarting.  Returning an
    // empty snapshot keeps the control endpoint responsive; reachability is
    // checked below so a live backend is not shown as stopped.
    return [];
  }
}

async function getSystemStatus(): Promise<SystemStatus> {
  if (systemStatusCache && systemStatusCache.expiresAt > Date.now()) {
    return systemStatusCache.value;
  }
  const [backendProcesses, frontendProcesses] = await Promise.all([
    getPortProcesses(backendPort),
    getPortProcesses(frontendPort)
  ]);
  const backendReachable = await canConnect(backendPort);
  let backendHealth = false;
  if (backendReachable) {
    try {
      const response = await fetch(`http://127.0.0.1:${backendPort}/api/health`, {
        signal: AbortSignal.timeout(900)
      });
      if (response.ok) {
        const payload = await response.json() as { service?: string; status?: string };
        backendHealth = payload.status === "ok" && payload.service === "热讯工坊";
      }
    } catch {
      backendHealth = false;
    }
  }
  // A reachable TCP port is not enough to claim that SignalForge is running:
  // it may belong to another process or be a stale socket during reload.
  const backendOwned = backendProcesses.some((item) => item.project_owned) || backendHealth;
  const backendOccupied = backendProcesses.length > 0 || backendReachable;
  // This code runs inside the Vite process that serves /local-control, so the
  // current frontend is known to be project-owned even when WMI briefly
  // returns no process row.
  const frontendOwned = true;
  // Native PID enumeration intentionally avoids the slow WMI command-line
  // lookup. Once the service identity is verified, attach that ownership to
  // the real listener rows so the UI does not label them as foreign PIDs.
  const ownedBackendProcesses = backendHealth
    ? backendProcesses.map((item) => ({ ...item, project_owned: true }))
    : backendProcesses;
  const ownedFrontendProcesses = frontendProcesses.map((item) => ({ ...item, project_owned: true }));

  const value: SystemStatus = {
    backend: {
      name: "backend",
      running: backendOwned,
      port_occupied: backendOccupied,
      port: backendPort,
      url: `http://127.0.0.1:${backendPort}`,
      processes: ownedBackendProcesses.length ? ownedBackendProcesses : backendHealth ? [{
        pid: 0,
        parent_pid: null,
        name: "SignalForge API",
        command_line: "http://127.0.0.1:" + backendPort + "/api/health",
        project_owned: true
      }] : [],
      can_start: !backendOccupied,
      can_stop: backendOwned
    },
    frontend: {
      name: "frontend",
      // This endpoint is served by the current Vite process, so it is a
      // reliable indicator even when Windows process enumeration lags.
      running: true,
      port_occupied: true,
      port: frontendPort,
      url: `http://127.0.0.1:${frontendPort}`,
      processes: ownedFrontendProcesses.length ? ownedFrontendProcesses : [{
        pid: process.pid,
        parent_pid: null,
        name: "node",
        command_line: "vite dev server",
        project_owned: true
      }],
      can_start: false,
      can_stop: frontendOwned
    },
    workspace: workspaceRoot,
    generated_at: new Date().toISOString()
  };
  // The settings page polls every five seconds; short caching prevents the
  // initial render and an immediate refresh from spawning duplicate WMI
  // queries, which are comparatively slow on Windows.
  systemStatusCache = { value, expiresAt: Date.now() + 1500 };
  return value;
}

function canConnect(port: number) {
  return new Promise<boolean>((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port }, () => {
      socket.end();
      resolve(true);
    });
    socket.setTimeout(500, () => {
      socket.destroy();
      resolve(false);
    });
    socket.on("error", () => resolve(false));
  });
}

async function waitForPort(port: number, expectedOpen: boolean, timeoutMs = 10_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if ((await canConnect(port)) === expectedOpen) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  return false;
}

async function startBackend() {
  systemStatusCache = null;
  const status = await getSystemStatus();
  if (status.backend.running) {
    return "Backend is already running.";
  }

  const venvPython =
    process.platform === "win32"
      ? path.join(workspaceRoot, ".venv", "Scripts", "python.exe")
      : path.join(workspaceRoot, ".venv", "bin", "python");
  const command = existsSync(venvPython) ? venvPython : "python";
  const args = [
    "-m",
    "uvicorn",
    "backend.app.main:app",
    "--reload",
    "--host",
    "127.0.0.1",
    "--port",
    String(backendPort)
  ];

  spawn(command, args, {
    cwd: workspaceRoot,
    detached: true,
    stdio: "ignore",
    windowsHide: true
  }).unref();

  const opened = await waitForPort(backendPort, true);
  // A listening socket can appear a moment before the child process metadata
  // is visible to PowerShell/WMI.  Do not report an ambiguous state during
  // that short startup window; verify ownership a few times before giving up.
  if (opened) {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      const nextStatus = await getSystemStatus();
      if (nextStatus.backend.running) {
        systemStatusCache = null;
        return "Backend started.";
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  const finalStatus = await getSystemStatus();
  if (finalStatus.backend.running) {
    systemStatusCache = null;
    return "Backend started.";
  }
  return opened ? "Backend port opened, but status could not be confirmed." : "Backend start was requested, but the port is not listening yet.";
}

async function stopBackend() {
  systemStatusCache = null;
  const status = await getSystemStatus();
  const pids = status.backend.processes.map((item) => item.pid).filter((pid) => pid > 0);
  let stopped = 0;
  if (process.platform === "win32") {
    // taskkill terminates the reloader and its worker in one call and avoids
    // the slow, failure-prone whole-machine WMI process-tree scan.
    for (const pid of new Set(pids)) {
      try {
        await execFileAsync("taskkill.exe", ["/PID", String(pid), "/T", "/F"], {
          windowsHide: true,
          timeout: 5000,
          maxBuffer: 256 * 1024
        });
        stopped += 1;
      } catch {
        // The process may have exited during reload; status verification below
        // determines whether the port was actually released.
      }
    }
  } else {
    for (const pid of new Set(pids)) {
      try {
        process.kill(pid, "SIGTERM");
        stopped += 1;
      } catch {
        // Ignore already-exited processes.
      }
    }
  }
  await waitForPort(backendPort, false, 8_000);
  systemStatusCache = null;
  const stillRunning = await canConnect(backendPort);
  return !stillRunning && (stopped || status.backend.port_occupied)
    ? `Backend stopped (${stopped || 1} process${(stopped || 1) > 1 ? "es" : ""}).`
    : "No project backend process was listening.";
}

function writeJson(res: { statusCode?: number; setHeader: (name: string, value: string) => void; end: (data?: string) => void }, body: unknown, statusCode = 200) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

function localControlPlugin() {
  return {
    name: "signalforge-local-control",
    configureServer(server: { middlewares: { use: (handler: (req: { method?: string; url?: string }, res: any, next: () => void) => void) => void } }) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://127.0.0.1");
        if (!url.pathname.startsWith("/local-control")) {
          next();
          return;
        }

        try {
          if (req.method === "GET" && url.pathname === "/local-control/status") {
            writeJson(res, await getSystemStatus());
            return;
          }

          if (req.method === "POST" && url.pathname === "/local-control/backend/start") {
            const message = await startBackend();
            writeJson(res, { ok: true, message, status: await getSystemStatus() });
            return;
          }

          if (req.method === "POST" && url.pathname === "/local-control/backend/stop") {
            const message = await stopBackend();
            writeJson(res, { ok: true, message, status: await getSystemStatus() });
            return;
          }

          if (req.method === "POST" && url.pathname === "/local-control/backend/restart") {
            const stopMessage = await stopBackend();
            const startMessage = await startBackend();
            writeJson(res, { ok: true, message: `${stopMessage} ${startMessage}`, status: await getSystemStatus() });
            return;
          }

          if (req.method === "POST" && url.pathname === "/local-control/frontend/stop") {
            writeJson(res, {
              ok: true,
              message: "Frontend is shutting down. Port 5173 will be released."
            });
            setTimeout(() => process.exit(0), 300);
            return;
          }

          if (req.method === "POST" && url.pathname === "/local-control/shutdown") {
            writeJson(res, {
              ok: true,
              message: "Shutdown requested. Backend and frontend are shutting down."
            });
            // Respond first so the browser can leave the loading state. The
            // current page remains visible after Vite exits, so this ordering
            // also lets the UI show a meaningful completed state.
            setTimeout(() => {
              void stopBackend().finally(() => process.exit(0));
            }, 100);
            return;
          }

          writeJson(res, { ok: false, message: "Unknown local control route." }, 404);
        } catch (error) {
          writeJson(
            res,
            {
              ok: false,
              message: error instanceof Error ? error.message : "Local control failed."
            },
            500
          );
        }
      });
    }
  };
}

export default defineConfig({
  plugins: [react(), localControlPlugin()],
  server: {
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true
      }
    }
  }
});
