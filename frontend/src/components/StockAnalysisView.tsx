import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, TrendingUp } from "lucide-react";
import { analyzeStocks, fetchStockSourcesHealth } from "../api";
import type { StockAnalysisResult } from "../types";
import MarkdownContent from "./MarkdownContent";

function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

export default function StockAnalysisView() {
  const [stocks, setStocks] = useState("600519");
  const [result, setResult] = useState<StockAnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [health, setHealth] = useState<{ status: string; libraries: Record<string, string>; credentials: Record<string, string>; retry_limit: number; cache_ttl_seconds: number } | null>(null);

  useEffect(() => { fetchStockSourcesHealth().then(setHealth).catch(() => setHealth(null)); }, []);

  async function handleAnalyze() {
    setBusy(true); setMessage(null);
    try { setResult(await analyzeStocks({ stocks })); }
    catch (err) { setMessage(err instanceof Error ? err.message : "股票分析失败"); }
    finally { setBusy(false); }
  }

  // 中文说明：函数「StockAnalysisView」负责完成该界面的状态处理、交互逻辑或数据转换。
  return <div className="single-view">
    <section className="panel action-panel"><div className="panel-heading"><div><h2>股票助手 · Stock Analysis Skill</h2><p>财经、股票和股票新闻请求默认调用此 Skill。支持 A 股、港股、美股。</p></div><button className="primary-button" onClick={handleAnalyze} disabled={busy || !stocks.trim()} type="button">{busy ? <Loader2 className="spin" size={18} /> : <TrendingUp size={18} />}<span>{busy ? "分析中" : "开始分析"}</span></button></div>
      <div className="form-grid"><label className="wide"><span>股票代码或名称（逗号分隔）</span><input value={stocks} onChange={(event) => setStocks(event.target.value)} placeholder="600519, TSLA, HK00700" /></label></div>
      {health && <div className="control-message"><CheckCircle2 size={16} /><span>数据源：{health.status === "ok" ? "可用" : "暂不可用"} · 重试 {health.retry_limit} 次 · 缓存 {health.cache_ttl_seconds} 秒</span></div>}
      {message && <div className="control-message"><AlertCircle size={16} /><span>{message}</span></div>}
    </section>
    {result && <section className="panel outputs-panel"><div className="panel-heading tight"><div><h2>股票决策看板</h2><p>数据脚本：{result.data_script} · 新闻抓取：{result.news_enabled ? "已启用" : "未启用"}</p></div></div>{result.data_status && <div className={cn("stock-data-status", result.data_status)}>{result.data_status === "ok" ? "数据完整" : result.data_status === "partial" ? "部分数据可用" : "数据暂不可用"}{result.source_status?.cache === "hit" ? " · 使用缓存" : ""}</div>}<MarkdownContent content={result.report} className="stock-report-markdown" /><p className="risk-note">{result.disclaimer}</p></section>}
  </div>;
}
