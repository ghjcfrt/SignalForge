import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** 合并条件样式名并过滤空值。 */
function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

/** 安全渲染模型返回的 Markdown 内容。 */
export default function MarkdownContent({ content, className }: { content: string; className?: string }) {
  /** 将模型生成的 Markdown 统一渲染到所有结果区域。 */
  return <div className={cn("markdown-content", className)}><ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ""}</ReactMarkdown></div>;
}
