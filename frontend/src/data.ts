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
  { id: "overview", label: "总览", icon: LayoutDashboard },
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
  { id: "scripts", label: "脚本工坊", icon: PenLine },
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
    owner: "赵爽",
    action: "搜集热点",
    description: "追踪 AI 圈与开源社区线索。"
  },
  {
    agentId: "viral_analyst",
    title: "爆款分析师",
    owner: "星辰",
    action: "拆解爆点",
    description: "判断钩子、冲突和传播风险。"
  },
  {
    agentId: "copywriter",
    title: "文案助手",
    owner: "洛一",
    action: "写脚本",
    description: "产出 90-120 秒口播脚本。"
  },
  {
    agentId: "video_editor",
    title: "视频剪辑员",
    owner: "小李",
    action: "做剪辑方案",
    description: "生成镜头、配音、字幕与导出设置。"
  },
  {
    agentId: "operator",
    title: "运营大师",
    owner: "尤道理",
    action: "发布复盘",
    description: "准备标题、封面、评论和指标。"
  }
];
