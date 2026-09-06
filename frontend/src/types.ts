export type AgentStatus = "online" | "idle" | "busy" | "offline";
export type WorkflowStatus = "queued" | "running" | "paused" | "completed" | "failed";
export type WorkflowStageStatus = "pending" | "running" | "completed" | "failed";

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
  model_available: boolean;
  diagnostic: string | null;
  key_preview?: string | null;
}

export interface TimeoutSettings {
  news_fetch_timeout_seconds: number;
  model_timeout_seconds: number;
  workflow_timeout_seconds: number;
}

export interface OutputDirectorySettings {
  video_output_dir: string;
  operator_output_dir: string;
}

export interface SecretSetting {
  configured: boolean;
  preview: string | null;
}

export interface EnvSettings {
  ai_api_key: SecretSetting;
  ai_base_url: string;
  ai_model: string;
  mpt_pexels_api_key: SecretSetting;
  backend_port: number;
  socialdatax_api_key: SecretSetting;
  socialdatax_base_url: string;
  socialdatax_timeout_seconds: number;
  tushare_token: SecretSetting;
  tavily_api_key: SecretSetting;
  serpapi_key: SecretSetting;
}

export interface ViralAnalysisConfig {
  source: "socialdatax" | "manual";
  enabled: boolean;
  manual_content: string;
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
  verification_status?: "verified" | "unverified";
  verification_note?: string;
  cross_check_note?: string;
  sources?: Array<{ name: string; url: string; published_at: string; claim: string }>;
}

export interface AgentOutput {
  agent_id: string;
  agent_name: string;
  title: string;
  content: string;
  artifact_path: string;
  created_at: string;
}

export interface WorkflowLog {
  timestamp: string;
  level: "info" | "warning" | "error";
  stage: string | null;
  message: string;
  detail: string | null;
}

export interface EngagementComment {
  id: string;
  author: string;
  content: string;
  source: string;
  time: string;
  category: "情绪支持" | "内容讨论" | "产品咨询";
  assignedAgentId: string;
  priority: "高" | "普通";
  status: "待回复" | "已回复";
}

export interface StockAnalysisResult {
  agent_id: string;
  skill: string;
  skill_source: string;
  stocks: string;
  report: string;
  raw_data: Record<string, unknown>;
  data_script: string;
  news_enabled: boolean;
  disclaimer: string;
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
  current_stage?: string | null;
  resumable?: boolean;
  source_status?: Record<string, string>;
  stage_status?: Record<string, WorkflowStageStatus>;
  logs?: WorkflowLog[];
  log_file?: string | null;
  viral_analysis?: ViralAnalysisConfig;
  selected_topic_title?: string | null;
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

export interface DirectorySelection {
  path: string;
}
