import { useEffect, useState } from "react";
import { HeartHandshake, MessageCircle } from "lucide-react";
import type { Agent, EngagementComment } from "../types";

/** 合并条件样式名并过滤空值。 */
function cn(...classes: Array<string | false | null | undefined>) { return classes.filter(Boolean).join(" "); }

const initialComments: EngagementComment[] = [
  { id: "c-101", author: "小树洞", content: "最近总是很焦虑，明明没有发生什么，却每天都觉得好累。该怎么办？", source: "视频评论区 · 《成年人如何面对焦虑》", time: "刚刚", category: "情绪支持", assignedAgentId: "healer", priority: "高", status: "待回复" },
  { id: "c-102", author: "Momo", content: "这个工作流可以接入小红书的评论吗？想用在自己的账号上。", source: "视频评论区 · 《AI 员工工作流》", time: "8 分钟前", category: "产品咨询", assignedAgentId: "operator", priority: "普通", status: "待回复" },
  { id: "c-103", author: "阿远", content: "如果想系统学习这套方法，建议先从哪个岗位开始？", source: "私信", time: "21 分钟前", category: "内容讨论", assignedAgentId: "product_manager", priority: "普通", status: "待回复" },
  { id: "c-104", author: "晚风", content: "看完视频感觉被理解了，谢谢你们认真做这样的内容。", source: "视频评论区 · 《给低能量的你》", time: "36 分钟前", category: "情绪支持", assignedAgentId: "healer", priority: "普通", status: "待回复" }
];

/** 互动管理页面，展示并发送评论回复。 */
export default function EngagementView({ agents }: { agents: Agent[] }) {
  const [comments, setComments] = useState(initialComments);
  const [selectedId, setSelectedId] = useState(initialComments[0].id);
  const [draft, setDraft] = useState("");
  const selected = comments.find((comment) => comment.id === selectedId) ?? comments[0];
  const agentName = (id: string) => agents.find((agent) => agent.id === id)?.title ?? id;

  useEffect(() => {
    if (!selected) return;
    setDraft(selected.status === "已回复" ? "已完成回复，可继续编辑" : selected.category === "情绪支持" ? "听起来你最近承受了不少压力，谢谢你愿意把这份感受说出来。可以先从今天最困扰你的一个小片段开始，给自己一点喘息的空间；如果这种疲惫持续影响生活，也建议找专业咨询师聊聊。" : "感谢你的留言，我们会把这个问题记录下来并持续完善。你也可以告诉我们更具体的使用场景。 ");
  }, [selectedId, selected?.status, selected?.category]);

  /** 提交一条互动回复并刷新回复状态。 */
  function sendReply() {
    if (!selected || !draft.trim() || selected.status === "已回复") return;
    setComments((items) => items.map((item) => item.id === selected.id ? { ...item, status: "已回复" } : item));
  }

  return (
    <div className="engagement-layout">
      <section className="panel engagement-queue">
        <div className="panel-heading tight">
          <div><h2>待处理互动</h2><p>按主题分派给对应员工，回复前请先确认语气和安全边界。</p></div>
          <span className="count-badge">{comments.filter((item) => item.status === "待回复").length} 待回复</span>
        </div>
        <div className="comment-list">
          {comments.map((comment) => (
            <button type="button" key={comment.id} className={cn("comment-row", selectedId === comment.id && "selected")} onClick={() => setSelectedId(comment.id)}>
              <div className="comment-avatar">{comment.author.slice(0, 1)}</div>
              <div className="comment-main"><div className="comment-meta"><strong>{comment.author}</strong><span>{comment.time}</span></div><p>{comment.content}</p><div className="comment-tags"><span>{comment.category}</span><span className={comment.priority === "高" ? "priority-high" : ""}>{comment.priority}</span></div></div>
              <div className={cn("reply-owner", comment.status === "已回复" && "replied")}><HeartHandshake size={14} /><span>{agentName(comment.assignedAgentId)}</span></div>
            </button>
          ))}
        </div>
      </section>
      <section className="panel reply-panel">
        {selected && <>
          <div className="panel-heading tight"><div><h2>回复工作台</h2><p>{selected.source}</p></div><span className={cn("reply-status", selected.status === "已回复" && "done")}>{selected.status}</span></div>
          <div className="selected-comment"><strong>{selected.author}</strong><p>{selected.content}</p></div>
          <label className="reply-label"><span>负责员工</span><select value={selected.assignedAgentId} onChange={(event) => setComments((items) => items.map((item) => item.id === selected.id ? { ...item, assignedAgentId: event.target.value } : item))}>{agents.filter((agent) => ["healer", "operator", "product_manager"].includes(agent.id)).map((agent) => <option key={agent.id} value={agent.id}>{agent.title}</option>)}</select></label>
          <label className="reply-label"><span>回复内容</span><textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={7} /></label>
          <div className="reply-footer"><span><MessageCircle size={15} /> 建议由 {agentName(selected.assignedAgentId)} 回复</span><button className="primary-button" type="button" onClick={sendReply} disabled={selected.status === "已回复" || !draft.trim()}>{selected.status === "已回复" ? "已提交" : "提交回复"}</button></div>
        </>}
      </section>
    </div>
  );
}
