export type AgentStatus = "online" | "idle" | "busy" | "offline";
export type WorkflowStatus = "queued" | "running" | "completed" | "failed";

export interface Skill {
  name: string;
  source: string;
  description: string;
}

export interface Agent {
  id: string;
  name: string;
  title: string;
  role: string;
  status: AgentStatus;
  focus: string;
  workspace: string;
  skills: Skill[];
}

export interface ApiStatus {
  key_variable: string;
  has_key: boolean;
  base_url: string;
  model: string;
  mode: "live" | "local-template";
}

export interface TopicSeed {
  domain: string;
  brief: string;
  audience: string;
  duration_seconds: number;
}

export interface Topic {
  title: string;
  heat: number;
  source_hint: string;
  angle: string;
  risk: string;
}

export interface AgentOutput {
  agent_id: string;
  agent_name: string;
  title: string;
  content: string;
  artifact_path: string;
  created_at: string;
}

export interface WorkflowRun {
  id: string;
  status: WorkflowStatus;
  seed: TopicSeed;
  topics: Topic[];
  outputs: AgentOutput[];
  run_dir: string;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface MoneyPrinterTurboStatus {
  installed: boolean;
  skill_dir: string;
  skill_file: string;
  helper_file: string;
  license_file: string;
  upstream: string;
  license: string;
  missing_env: string[];
  default_command: string;
}

export interface MoneyPrinterTurboRunResult {
  exit_code: number;
  status: "completed" | "needs_input" | "failed" | "missing_skill" | "timeout";
  stdout: string;
  stderr: string;
  video_files: string[];
  task_dir: string | null;
  log_file: string | null;
  result_file: string | null;
}

export interface ManagedProcess {
  pid: number;
  parent_pid: number | null;
  name: string;
  command_line: string;
  project_owned: boolean;
}

export interface ManagedServiceStatus {
  name: "backend" | "frontend";
  running: boolean;
  port_occupied: boolean;
  port: number;
  url: string;
  processes: ManagedProcess[];
  can_start: boolean;
  can_stop: boolean;
}

export interface SystemStatus {
  backend: ManagedServiceStatus;
  frontend: ManagedServiceStatus;
  workspace: string;
  generated_at: string;
}

export interface ControlResult {
  ok: boolean;
  message: string;
  status?: SystemStatus;
}
