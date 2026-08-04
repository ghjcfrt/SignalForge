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
  { id: "radar", label: "热点雷达", icon: Radio },
  { id: "stocks", label: "股票分析", icon: TrendingUp },
  { id: "scripts", label: "脚本工坊", icon: PenLine },
  { id: "editing", label: "剪辑队列", icon: Clapperboard },
  { id: "engagement", label: "互动回复", icon: MessageCircle },
  { id: "agents", label: "员工", icon: UsersRound },
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
