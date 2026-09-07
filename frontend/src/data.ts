/*
 * @Author: ghjcfrt 73391769+ghjcfrt@users.noreply.github.com
 * @Date: 2026-07-18 14:51:10
 * @LastEditors: ghjcfrt 73391769+ghjcfrt@users.noreply.github.com
 * @LastEditTime: 2026-09-08 04:01:21
 * @FilePath: \SignalForge\frontend\src\data.ts
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
 */
import {
  Bot,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  Clapperboard,
  Code2,
  HeartHandshake,
  LayoutDashboard,
  MessageCircle,
  Megaphone,
  Newspaper,
  PenLine,
  Radio,
  Settings,
  TrendingUp,
  UsersRound
} from "lucide-react";

export const navItems = [
  { id: "overview", label: "控制台", icon: LayoutDashboard },
  { id: "agent_hotspot_monitor", label: "热点监控员", icon: Newspaper },
  { id: "agent_viral_analyst", label: "爆款分析师", icon: ChartNoAxesCombined },
  { id: "agent_copywriter", label: "文案助手", icon: PenLine },
  { id: "agent_video_editor", label: "视频剪辑员", icon: Clapperboard },
  { id: "agent_operator", label: "运营大师", icon: Megaphone },
  { id: "agent_product_manager", label: "产品经理", icon: BriefcaseBusiness },
  { id: "agent_programmer", label: "程序员", icon: Code2 },
  { id: "agent_stock_assistant", label: "股票助手", icon: TrendingUp },
  { id: "agent_healer", label: "心理疗愈师", icon: HeartHandshake },
  { id: "radar", label: "热点雷达", icon: Radio },
  { id: "stocks", label: "股票分析", icon: TrendingUp },
  { id: "editing", label: "剪辑队列", icon: Clapperboard },
  { id: "engagement", label: "互动回复", icon: MessageCircle },
  { id: "settings", label: "设置", icon: Settings }
] as const;

export const roleIcons: Record<string, typeof Bot> = {
  hotspot_monitor: Newspaper,
  viral_analyst: ChartNoAxesCombined,
  copywriter: PenLine,
  video_editor: Clapperboard,
  operator: Megaphone,
  product_manager: BriefcaseBusiness,
  programmer: Code2,
  stock_assistant: TrendingUp,
  healer: HeartHandshake
};

export const pipeline = [
  {
    agentId: "hotspot_monitor",
    title: "热点监控员",
    action: "搜集热点",
    description: "独立搜集、排序并核验热点候选。"
  },
  {
    agentId: "viral_analyst",
    title: "爆款分析师",
    action: "拆解爆点",
    description: "判断钩子、冲突和传播风险。"
  },
  {
    agentId: "copywriter",
    title: "文案助手",
    action: "写脚本",
    description: "产出短视频口播脚本"
  },
  {
    agentId: "video_editor",
    title: "视频剪辑员",
    action: "做剪辑方案",
    description: "生成剪辑、字幕和配音方案。"
  },
  {
    agentId: "operator",
    title: "运营大师",
    action: "发布复盘",
    description: "准备标题、封面、评论和指标。"
  }
];
