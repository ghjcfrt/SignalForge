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
      windowsHide: true
    }
  );
  return stdout.trim();
}

function normalizeProcessList(raw: string): ManagedProcess[] {
  if (!raw) {
    return [];
  }
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [parsed];
}

async function getPortProcesses(port: number): Promise<ManagedProcess[]> {
  const root = psString(workspaceRoot);
  const script = `
$portValue = ${port}
$root = ${root}
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
      project_owned = $cmd.Contains($root)
    }
  }
}
@($items) | ConvertTo-Json -Depth 4
`;
  return normalizeProcessList(await runPowerShell(script));
}

async function getSystemStatus(): Promise<SystemStatus> {
  const [backendProcesses, frontendProcesses] = await Promise.all([
    getPortProcesses(backendPort),
    getPortProcesses(frontendPort)
  ]);
  const backendOwned = backendProcesses.some((item) => item.project_owned);
  const frontendOwned = frontendProcesses.some((item) => item.pid === process.pid || item.project_owned);

  return {
    backend: {
      name: "backend",
      running: backendOwned,
      port_occupied: backendProcesses.length > 0,
      port: backendPort,
      url: `http://127.0.0.1:${backendPort}`,
      processes: backendProcesses,
      can_start: backendProcesses.length === 0,
      can_stop: backendOwned
    },
    frontend: {
      name: "frontend",
      running: true,
      port_occupied: frontendProcesses.length > 0,
      port: frontendPort,
      url: `http://127.0.0.1:${frontendPort}`,
      processes: frontendProcesses.length
        ? frontendProcesses
        : [
            {
              pid: process.pid,
              parent_pid: null,
              name: "node",
              command_line: "vite dev server",
              project_owned: true
            }
          ],
      can_start: false,
      can_stop: frontendOwned
    },
    workspace: workspaceRoot,
    generated_at: new Date().toISOString()
  };
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
  const nextStatus = await getSystemStatus();
  if (nextStatus.backend.running) {
    return "Backend started.";
  }
  return opened ? "Backend port opened, but status could not be confirmed." : "Backend start was requested, but the port is not listening yet.";
}

async function stopBackend() {
  const root = psString(workspaceRoot);
  const script = `
$root = ${root}
$portValue = ${backendPort}
$all = @(Get-CimInstance Win32_Process)
$targets = New-Object 'System.Collections.Generic.HashSet[int]'
function Add-Tree([int]$pidValue) {
  if ($targets.Add($pidValue)) {
    foreach ($child in @($all | Where-Object { [int]$_.ParentProcessId -eq $pidValue })) {
      Add-Tree([int]$child.ProcessId)
    }
  }
}
$portPids = @(Get-NetTCPConnection -LocalPort $portValue -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' -and [int]$_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($pidValue in $portPids) {
  $proc = $all | Where-Object { [int]$_.ProcessId -eq [int]$pidValue } | Select-Object -First 1
  if ($proc) {
    $cmd = [string]$proc.CommandLine
    if ($cmd.Contains($root) -and ($cmd.Contains('uvicorn') -or $cmd.Contains('backend.app.main') -or $cmd.Contains('dev-backend.ps1') -or $cmd.Contains('.venv'))) {
      Add-Tree([int]$proc.ProcessId)
    }
  }
}
foreach ($proc in $all) {
  if ([int]$proc.ProcessId -eq [int]$PID) {
    continue
  }
  $cmd = [string]$proc.CommandLine
  if ($cmd.Contains($root) -and ($cmd.Contains('dev-backend.ps1') -or ($cmd.Contains('uvicorn') -and $cmd.Contains('backend.app.main')))) {
    Add-Tree([int]$proc.ProcessId)
  }
}
$stopped = foreach ($pidValue in @($targets)) {
  try {
    Stop-Process -Id $pidValue -Force -ErrorAction Stop
    [int]$pidValue
  } catch {}
}
[pscustomobject]@{ stopped = @($stopped) } | ConvertTo-Json -Depth 4
`;
  const raw = await runPowerShell(script);
  const result = raw ? JSON.parse(raw) : { stopped: [] };
  await waitForPort(backendPort, false, 8_000);
  const stopped = Array.isArray(result.stopped) ? result.stopped.length : result.stopped ? 1 : 0;
  return stopped ? `Backend stopped (${stopped} process${stopped > 1 ? "es" : ""}).` : "No project backend process was listening.";
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
