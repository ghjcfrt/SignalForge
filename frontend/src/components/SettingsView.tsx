import { useEffect, useRef, useState } from "react";
import { Bot, CircleDot, ExternalLink, FileText, KeyRound, Loader2, Plus, RefreshCcw, Save, Server } from "lucide-react";
import { exportWorkflow, fetchEnvSettings, fetchOutputDirectorySettings, fetchSystemStatus, fetchTimeoutSettings, importWorkflow, restartBackend, selectDirectory, startBackend, stopBackend, stopFrontend, updateEnvSettings, updateOutputDirectorySettings, updateTimeoutSettings } from "../api";
import type { ApiStatus, EnvSettings, OutputDirectorySettings, SystemStatus, TimeoutSettings, ViralAnalysisConfig, WorkflowRun } from "../types";
import ServiceCard, { type ControlAction } from "./ServiceCard";

// 设置页表单的默认超时值。
const defaultTimeoutSettings: TimeoutSettings = { news_fetch_timeout_seconds: 90, model_timeout_seconds: 30, workflow_timeout_seconds: 300 };
function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

/** 设置页面，管理环境变量、超时、输出目录和本地服务。 */
export default function SettingsView({ status, currentRun, onImport, onProjectMessage, onBackendStateChange, systemStatusSnapshot, onSystemStatusSnapshotChange, viralAnalysis, onViralAnalysisChange }: { status: ApiStatus | null; currentRun: WorkflowRun | null; onImport: (run: WorkflowRun) => void; onProjectMessage: (message: string) => void; onBackendStateChange: () => void; systemStatusSnapshot: SystemStatus | null; onSystemStatusSnapshotChange: (status: SystemStatus) => void; viralAnalysis: ViralAnalysisConfig; onViralAnalysisChange: (config: ViralAnalysisConfig) => void }) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(systemStatusSnapshot);
  const [controlBusy, setControlBusy] = useState<ControlAction | null>(null);
  const [serviceMessage, setServiceMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [timeoutSettings, setTimeoutSettings] = useState<TimeoutSettings | null>(null);
  const [timeoutDraft, setTimeoutDraft] = useState<TimeoutSettings>(defaultTimeoutSettings);
  const [unlimitedTimeouts, setUnlimitedTimeouts] = useState({ news: false, model: false, workflow: false });
  const [timeoutBusy, setTimeoutBusy] = useState(false);
  const [timeoutMessage, setTimeoutMessage] = useState<string | null>(null);
  const [outputDirs, setOutputDirs] = useState<OutputDirectorySettings>({ video_output_dir: "", operator_output_dir: "" });
  const [outputDirBusy, setOutputDirBusy] = useState(false);
  const [outputDirMessage, setOutputDirMessage] = useState<string | null>(null);
  const [envSettings, setEnvSettings] = useState<EnvSettings | null>(null);
  const [envDraft, setEnvDraft] = useState({ ai_api_key: "", ai_base_url: "", ai_model: "", mpt_pexels_api_key: "", backend_port: 8017, socialdatax_api_key: "", socialdatax_base_url: "", socialdatax_timeout_seconds: 60, tushare_token: "", tavily_api_key: "", serpapi_key: "" });
  const [envBusy, setEnvBusy] = useState(false);
  const [envMessage, setEnvMessage] = useState<string | null>(null);
  const [activeEnvCategory, setActiveEnvCategory] = useState<"ai" | "other" | "optional" | null>(null);

  /** 将服务端超时设置同步到页面表单状态。 */
  function applyTimeoutSettings(next: TimeoutSettings) {
    setTimeoutSettings(next);
    setTimeoutDraft({
      news_fetch_timeout_seconds: next.news_fetch_timeout_seconds || defaultTimeoutSettings.news_fetch_timeout_seconds,
      model_timeout_seconds: next.model_timeout_seconds || defaultTimeoutSettings.model_timeout_seconds,
      workflow_timeout_seconds: next.workflow_timeout_seconds === 0 ? defaultTimeoutSettings.workflow_timeout_seconds : next.workflow_timeout_seconds
    });
    setUnlimitedTimeouts({
      news: next.news_fetch_timeout_seconds === 0,
      model: next.model_timeout_seconds === 0,
      workflow: next.workflow_timeout_seconds === 0
    });
  }

  /** 更新单个超时字段并限制为合法整数。 */
  function updateTimeoutDraft(field: keyof TimeoutSettings, value: string) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setTimeoutDraft((current) => ({ ...current, [field]: Math.max(1, Math.floor(parsed)) }));
  }

  /** 切换新闻或模型调用是否不限时。 */
  function toggleUnlimited(field: "news" | "model", enabled: boolean) {
    setUnlimitedTimeouts((current) => ({ ...current, [field]: enabled }));
    if (!enabled) {
      const draftField = field === "news" ? "news_fetch_timeout_seconds" : "model_timeout_seconds";
      setTimeoutDraft((current) => ({
        ...current,
        [draftField]: current[draftField] || defaultTimeoutSettings[draftField]
      }));
    }
  }

  /** 执行前端界面逻辑。 */
  async function handleTimeoutSave() {
    setTimeoutBusy(true);
    setTimeoutMessage(null);
    try {
      const saved = await updateTimeoutSettings({
        news_fetch_timeout_seconds: unlimitedTimeouts.news ? 0 : timeoutDraft.news_fetch_timeout_seconds,
        model_timeout_seconds: unlimitedTimeouts.model ? 0 : timeoutDraft.model_timeout_seconds,
        workflow_timeout_seconds: unlimitedTimeouts.workflow ? 0 : timeoutDraft.workflow_timeout_seconds
      });
      applyTimeoutSettings(saved);
      setTimeoutMessage("热点扫描超时设置已保存");
    } catch (err) {
      setTimeoutMessage(err instanceof Error ? err.message : "保存超时设置失败");
    } finally {
      setTimeoutBusy(false);
    }
  }

  /** 执行前端界面逻辑。 */
  async function handleExport() {
    if (!currentRun) { onProjectMessage("当前没有可导出的项目"); return; }
    try {
      const data = await exportWorkflow(currentRun.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `signalforge-${currentRun.id}.json`;
      link.click();
      URL.revokeObjectURL(url);
      onProjectMessage("项目已导出");
    } catch (err) { onProjectMessage(err instanceof Error ? err.message : "导出失败"); }
  }

  /** 执行前端界面逻辑。 */
  async function handleImport(file: File | undefined) {
    if (!file) return;
    try {
      const imported = await importWorkflow(file);
      onImport(imported);
      // 立即同步选定主题和浏览器检查点，避免概览被旧的本地状态覆盖。
      onProjectMessage("项目已导入");
    }
    catch (err) { onProjectMessage(err instanceof Error ? err.message : "导入失败"); }
  }

  /** 执行前端界面逻辑。 */
  async function refreshSystemStatus() {
    const next = await fetchSystemStatus();
    setSystemStatus(next);
    onSystemStatusSnapshotChange(next);
    // PowerShell/WMI 的瞬时失败在后续刷新成功后不应继续固定显示在面板中。
    setServiceMessage(null);
    return next;
  }

  useEffect(() => {
    if (systemStatusSnapshot) setSystemStatus(systemStatusSnapshot);
  }, [systemStatusSnapshot]);

  useEffect(() => {
    if (!systemStatusSnapshot) refreshSystemStatus().catch((err: Error) => setServiceMessage(err.message));
  }, []);

  useEffect(() => {
    fetchOutputDirectorySettings().then(setOutputDirs).catch((err: Error) => setOutputDirMessage(err.message));
  }, []);

  useEffect(() => {
    fetchEnvSettings().then((next) => {
      setEnvSettings(next);
      setEnvDraft((current) => ({ ...current, ai_base_url: next.ai_base_url, ai_model: next.ai_model, backend_port: next.backend_port, socialdatax_base_url: next.socialdatax_base_url, socialdatax_timeout_seconds: next.socialdatax_timeout_seconds }));
    }).catch((err: Error) => setEnvMessage(err.message));
  }, []);

  /** 执行前端界面逻辑。 */
  async function handleEnvSave() {
    setEnvBusy(true); setEnvMessage(null);
    try {
      const saved = await updateEnvSettings(envDraft);
      const savedDirs = await updateOutputDirectorySettings(outputDirs);
      setEnvSettings(saved);
      setOutputDirs(savedDirs);
      setEnvDraft((current) => ({ ...current, ai_api_key: "", mpt_pexels_api_key: "", socialdatax_api_key: "", tushare_token: "", tavily_api_key: "", serpapi_key: "", ai_base_url: saved.ai_base_url, ai_model: saved.ai_model, backend_port: saved.backend_port, socialdatax_base_url: saved.socialdatax_base_url, socialdatax_timeout_seconds: saved.socialdatax_timeout_seconds }));
      setEnvMessage("运行配置已保存；密钥仅在填写新值时更新");
      onBackendStateChange();
    } catch (err) { setEnvMessage(err instanceof Error ? err.message : "保存运行配置失败"); }
    finally { setEnvBusy(false); }
  }

  /** 执行前端界面逻辑。 */
  async function handleOutputDirSave() {
    setOutputDirBusy(true); setOutputDirMessage(null);
    try {
      const saved = await updateOutputDirectorySettings(outputDirs);
      setOutputDirs(saved); setOutputDirMessage("产物目录已保存");
    } catch (err) { setOutputDirMessage(err instanceof Error ? err.message : "保存产物目录失败"); }
    finally { setOutputDirBusy(false); }
  }

  /** 执行前端界面逻辑。 */
  async function handleDirectorySelect(field: keyof OutputDirectorySettings) {
    try {
      const selected = await selectDirectory();
      if (selected.path) setOutputDirs((current) => ({ ...current, [field]: selected.path }));
    } catch (err) { setEnvMessage(err instanceof Error ? err.message : "选择目录失败"); }
  }

  useEffect(() => {
    fetchTimeoutSettings()
      .then(applyTimeoutSettings)
      .catch((err: Error) => setTimeoutMessage(err.message));
  }, []);

  /** 执行前端界面逻辑。 */
  async function handleControl(action: ControlAction) {
    const confirmation =
      action === "frontend-stop"
        ? "关闭前端后，当前页面会失去响应，5173 端口将被释放。确定继续吗？"
        : action === "backend-stop"
          ? "关闭后端会中断正在运行的工作流和 API 请求。确定继续吗？"
          : action === "backend-restart"
            ? "重启后端会短暂中断 API 请求。确定继续吗？"
            : null;
    if (confirmation && !window.confirm(confirmation)) {
      return;
    }

    setControlBusy(action);
    setServiceMessage(null);
    try {
      const result =
        action === "backend-start"
          ? await startBackend()
          : action === "backend-stop"
            ? await stopBackend()
            : action === "backend-restart"
              ? await restartBackend()
              : await stopFrontend();
      setServiceMessage(result.message);
      if (result.status) {
        setSystemStatus(result.status);
        onSystemStatusSnapshotChange(result.status);
      } else if (action !== "frontend-stop") {
        await refreshSystemStatus();
      }
      if (action.startsWith("backend-")) {
        onBackendStateChange();
      }
    } catch (err) {
      setServiceMessage(err instanceof Error ? err.message : "控制命令失败");
    } finally {
      setControlBusy(null);
    }
  }

  return (
    <div className={`single-view settings-page-shell${activeEnvCategory ? " subpage" : ""}`}>
      <div className="settings-overview-grid">
      <section className="panel settings-panel runtime-settings-panel">
        <div className="panel-heading tight"><div><h2>运行配置</h2><p>仅显示已配置密钥的首尾字符，中间内容始终打码。</p></div></div>
        <div className="settings-list">
          <div><KeyRound size={18} /><span>Key Path</span><strong>{status?.key_preview ?? "未配置"}</strong></div>
          <div><ExternalLink size={18} /><span>Base URL</span><strong>{status?.base_url ?? "https://api.openlux.ai/v1"}</strong></div>
          <div><Bot size={18} /><span>Model</span><strong>{status?.model ?? "中转站自动选择"}</strong></div>
          <div><FileText size={18} /><span>AI Health</span><strong>{status ? (status.model_available ? "模型可用" : "模型不可用") : "检查中"}</strong></div>
        </div>
      </section>
      <section className="panel settings-panel project-settings-panel">
        <div className="panel-heading tight">
          <div><h2>项目文件</h2><p>手动保存或恢复热点、产物和流水线进度。</p></div>
        </div>
        <div className="project-file-actions">
          <button className="primary-button" type="button" onClick={handleExport}><FileText size={17} /><span>导出项目</span></button>
          <button className="ghost-button" type="button" onClick={() => fileInputRef.current?.click()}><RefreshCcw size={17} /><span>导入项目</span></button>
          <input ref={fileInputRef} type="file" accept="application/json,.json" hidden onChange={(event) => handleImport(event.target.files?.[0])} />
        </div>
      </section>
      <section className="panel settings-panel project-config-panel">
        <div className="panel-heading tight"><div><h2>项目配置</h2><p>管理本项目的运行参数和可选服务。</p></div></div>
        <div className="env-category-actions">
          <button className="ghost-button" type="button" onClick={() => setActiveEnvCategory("ai")}><Bot size={17} /><span>AI 配置</span></button>
          <button className="ghost-button" type="button" onClick={() => setActiveEnvCategory("other")}><Server size={17} /><span>其他配置</span></button>
          <button className="ghost-button" type="button" onClick={() => setActiveEnvCategory("optional")}><Plus size={17} /><span>可选配置</span></button>
        </div>
      </section>
      </div>
      {activeEnvCategory && <section className="panel settings-panel env-settings-panel" data-category={activeEnvCategory}>
        <div className="panel-heading tight"><div><h2>{activeEnvCategory === "ai" ? "AI 配置" : activeEnvCategory === "other" ? "其他配置" : "可选配置"}</h2><p>已配置密钥只显示掩码；密钥输入框留空表示保留原值。端口变更需重启后端后生效。</p></div><button className="ghost-button inline" type="button" onClick={() => setActiveEnvCategory(null)}>返回项目设置</button></div>
        <div className="timeout-grid">
          <label className="timeout-field"><span className="timeout-label">AI Base URL</span><input value={envDraft.ai_base_url} onChange={(e) => setEnvDraft({ ...envDraft, ai_base_url: e.target.value })} placeholder="https://api.openlux.ai/v1" /></label>
          <label className="timeout-field"><span className="timeout-label">AI Model</span><input value={envDraft.ai_model} onChange={(e) => setEnvDraft({ ...envDraft, ai_model: e.target.value })} placeholder="留空自动选择" /></label>
          <label className="timeout-field"><span className="timeout-label">后端端口</span><input type="number" min="1" max="65535" value={envDraft.backend_port} onChange={(e) => setEnvDraft({ ...envDraft, backend_port: Number(e.target.value) || 8017 })} /></label>
          <label className="timeout-field"><span className="timeout-label">AI API Key {envSettings?.ai_api_key.configured && <small><br />（当前 {envSettings.ai_api_key.preview}）</small>}</span><input type="password" value={envDraft.ai_api_key} onChange={(e) => setEnvDraft({ ...envDraft, ai_api_key: e.target.value })} placeholder="留空保留现有密钥" autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">Pexels Key {envSettings?.mpt_pexels_api_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.mpt_pexels_api_key} onChange={(e) => setEnvDraft({ ...envDraft, mpt_pexels_api_key: e.target.value })} placeholder="可选" autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">SocialDataX Base URL</span><input value={envDraft.socialdatax_base_url} onChange={(e) => setEnvDraft({ ...envDraft, socialdatax_base_url: e.target.value })} /></label>
          <label className="timeout-field"><span className="timeout-label">SocialDataX API Key {envSettings?.socialdatax_api_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.socialdatax_api_key} onChange={(e) => setEnvDraft({ ...envDraft, socialdatax_api_key: e.target.value })} placeholder="可选" autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">SocialDataX 超时（秒）</span><input type="number" min="0" value={envDraft.socialdatax_timeout_seconds} onChange={(e) => setEnvDraft({ ...envDraft, socialdatax_timeout_seconds: Math.max(0, Number(e.target.value) || 0) })} /></label>
          {activeEnvCategory === "other" && <>
            <div className="timeout-field directory-field"><span className="timeout-label">视频输出目录</span><div className="directory-picker-row"><span className="directory-value">{outputDirs.video_output_dir || "未选择"}</span><button className="ghost-button" type="button" onClick={() => handleDirectorySelect("video_output_dir")}>选择目录</button></div><span className="timeout-hint">MP4 成片及视频剪辑产物</span></div>
            <div className="timeout-field directory-field"><span className="timeout-label">运营大师输出目录</span><div className="directory-picker-row"><span className="directory-value">{outputDirs.operator_output_dir || "未选择"}</span><button className="ghost-button" type="button" onClick={() => handleDirectorySelect("operator_output_dir")}>选择目录</button></div><span className="timeout-hint">标题、封面文案、发布时间和复盘指标</span></div>
            <div className="other-config-block">
              <div className="other-config-heading"><div><strong>爆款分析</strong><span>这里只影响总控制台流水线；<br />员工独立工作台有各自设置。</span></div></div>
              <label className="switch-line switch-control"><input type="checkbox" checked={viralAnalysis.enabled} onChange={(event) => onViralAnalysisChange({ ...viralAnalysis, enabled: event.target.checked })} /><span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span><span className="switch-copy"><strong>{viralAnalysis.enabled ? "已启用" : "已关闭"}</strong><small>控制台流水线是否执行爆款分析阶段</small></span></label>
              <div className="segmented-control"><button className={cn("segment-button", viralAnalysis.source === "socialdatax" && "selected")} onClick={() => onViralAnalysisChange({ ...viralAnalysis, source: "socialdatax" })} type="button">SocialDataX</button><button className={cn("segment-button", viralAnalysis.source === "manual" && "selected")} onClick={() => onViralAnalysisChange({ ...viralAnalysis, source: "manual" })} type="button">手写分析</button></div>
              {viralAnalysis.source === "manual" && <label><span>手写分析依据</span><textarea value={viralAnalysis.manual_content} onChange={(event) => onViralAnalysisChange({ ...viralAnalysis, manual_content: event.target.value })} placeholder="填写总控制台本轮使用的样本或分析依据" /></label>}
            </div>
          </>}
        </div>
        <details className="env-advanced"><summary>股票新闻服务密钥（可选）</summary><div className="timeout-grid">
          <label className="timeout-field"><span className="timeout-label">Tushare Token {envSettings?.tushare_token.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.tushare_token} onChange={(e) => setEnvDraft({ ...envDraft, tushare_token: e.target.value })} autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">Tavily API Key {envSettings?.tavily_api_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.tavily_api_key} onChange={(e) => setEnvDraft({ ...envDraft, tavily_api_key: e.target.value })} autoComplete="new-password" /></label>
          <label className="timeout-field"><span className="timeout-label">SerpAPI Key {envSettings?.serpapi_key.configured && <small>（已配置）</small>}</span><input type="password" value={envDraft.serpapi_key} onChange={(e) => setEnvDraft({ ...envDraft, serpapi_key: e.target.value })} autoComplete="new-password" /></label>
        </div></details>
        <div className="timeout-actions"><button className="primary-button" type="button" onClick={handleEnvSave} disabled={envBusy || !envSettings}><Save size={17} /><span>{envBusy ? "保存中" : "保存运行配置"}</span></button>{envMessage && <span className="timeout-message">{envMessage}</span>}</div>
      </section>}
      {false && <section className="panel settings-panel output-directory-panel">
        <div className="panel-heading tight"><div><h2>产物输出目录</h2><p>可填写绝对路径；留空则使用项目默认目录。视频会复制到视频目录，运营大师的标题、封面文案和复盘指标会保存到运营目录。</p></div></div>
        <div className="timeout-grid">
          <label className="timeout-field"><span className="timeout-label">视频输出目录</span><input value={outputDirs.video_output_dir} onChange={(event) => setOutputDirs({ ...outputDirs, video_output_dir: event.target.value })} placeholder="例如 D:\\Videos\\SignalForge" /><span className="timeout-hint">MP4 成片及视频剪辑产物</span></label>
          <label className="timeout-field"><span className="timeout-label">运营大师输出目录</span><input value={outputDirs.operator_output_dir} onChange={(event) => setOutputDirs({ ...outputDirs, operator_output_dir: event.target.value })} placeholder="例如 D:\\Content\\运营方案" /><span className="timeout-hint">标题、封面文案、发布时间和复盘指标</span></label>
        </div>
        <div className="timeout-actions"><button className="primary-button" type="button" onClick={handleOutputDirSave} disabled={outputDirBusy}><Save size={17} /><span>{outputDirBusy ? "保存中" : "保存产物目录"}</span></button>{outputDirMessage && <span className="timeout-message">{outputDirMessage}</span>}</div>
      </section>}
      <div className="settings-management-grid">
      <section className="panel settings-panel timeout-settings-panel">
        <div className="panel-heading tight">
          <div>
            <h2>热点扫描超时</h2>
            <p>控制公开来源抓取和模型整理的等待时间，0 表示不限时；视频剪辑员成片渲染始终不限时。</p>
          </div>
        </div>
        <div className="timeout-grid">
          <label className="timeout-field">
            <span className="timeout-label">公开来源抓取</span>
            <div className="timeout-input-row">
              <input
                type="number"
                min="1"
                step="1"
                value={unlimitedTimeouts.news ? "" : timeoutDraft.news_fetch_timeout_seconds}
                disabled={timeoutSettings === null || unlimitedTimeouts.news}
                onChange={(event) => updateTimeoutDraft("news_fetch_timeout_seconds", event.target.value)}
              />
              <span>秒</span>
            </div>
            <span className="timeout-hint">Skill 多来源抓取</span>
            <span className="timeout-toggle">
              <input
                type="checkbox"
                checked={unlimitedTimeouts.news}
                disabled={timeoutSettings === null}
                onChange={(event) => toggleUnlimited("news", event.target.checked)}
              />
              <span>不限时</span>
            </span>
          </label>
          <label className="timeout-field">
            <span className="timeout-label">工作流总时限</span>
            <div className="timeout-input-row">
              <input
                type="number"
                min="1"
                max="86400"
                step="1"
                value={unlimitedTimeouts.workflow ? "" : timeoutDraft.workflow_timeout_seconds}
                disabled={timeoutSettings === null || unlimitedTimeouts.workflow}
                onChange={(event) => updateTimeoutDraft("workflow_timeout_seconds", event.target.value)}
              />
              <span>秒</span>
            </div>
            <span className="timeout-hint">超时后保留检查点，可继续执行</span>
            <span className="timeout-toggle">
              <input
                type="checkbox"
                checked={unlimitedTimeouts.workflow}
                disabled={timeoutSettings === null}
                onChange={(event) => setUnlimitedTimeouts((current) => ({ ...current, workflow: event.target.checked }))}
              />
              <span>不限时</span>
            </span>
          </label>
          <label className="timeout-field">
            <span className="timeout-label">模型整理</span>
            <div className="timeout-input-row">
              <input
                type="number"
                min="1"
                step="1"
                value={unlimitedTimeouts.model ? "" : timeoutDraft.model_timeout_seconds}
                disabled={timeoutSettings === null || unlimitedTimeouts.model}
                onChange={(event) => updateTimeoutDraft("model_timeout_seconds", event.target.value)}
              />
              <span>秒</span>
            </div>
            <span className="timeout-hint">AI 生成热点候选</span>
            <span className="timeout-toggle">
              <input
                type="checkbox"
                checked={unlimitedTimeouts.model}
                disabled={timeoutSettings === null}
                onChange={(event) => toggleUnlimited("model", event.target.checked)}
              />
              <span>不限时</span>
            </span>
          </label>
        </div>
        <div className="timeout-actions">
          <button className="primary-button" type="button" onClick={handleTimeoutSave} disabled={timeoutBusy || timeoutSettings === null}>
            <Save size={17} />
            <span>{timeoutBusy ? "保存中" : "保存超时设置"}</span>
          </button>
          {timeoutMessage && <span className="timeout-message">{timeoutMessage}</span>}
        </div>
      </section>
      <section className="panel service-panel">
        <div className="panel-heading tight">
          <div>
            <h2>本地服务控制</h2>
            <p>查看端口占用，启动、关闭或重启本项目的后端和前端。</p>
          </div>
          <button className="ghost-button inline" onClick={() => refreshSystemStatus().catch((err: Error) => setServiceMessage(err.message))} disabled={controlBusy !== null}>
            <RefreshCcw size={16} />
            <span>刷新状态</span>
          </button>
        </div>
        {serviceMessage && (
          <div className="control-message">
            <CircleDot size={16} />
            <span>{serviceMessage}</span>
          </div>
        )}
        <div className="service-grid">
          {systemStatus ? (
            <>
              <ServiceCard service={systemStatus.backend} busyAction={controlBusy} onAction={handleControl} />
              <ServiceCard service={systemStatus.frontend} busyAction={controlBusy} onAction={handleControl} />
            </>
          ) : (
            <div className="empty-state">
              <Loader2 className="spin" size={20} />
              <span>正在读取本地服务状态。</span>
            </div>
          )}
        </div>
      </section>
      </div>
    </div>
  );
}
