import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

export default function MarkdownContent({ content, className }: { content: string; className?: string }) {
  /** Render model-produced Markdown consistently across every result surface. */
  // 中文说明：函数「MarkdownContent」负责完成该界面的状态处理、交互逻辑或数据转换。
  return <div className={cn("markdown-content", className)}><ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ""}</ReactMarkdown></div>;
}
