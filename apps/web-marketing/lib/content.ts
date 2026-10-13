/**
 * CMS 内容类型定义。
 * 所有页面内容来自 content/*.json（运营改 JSON 不改代码）。
 * 类型在构建期对 JSON 做静态校验（resolveJsonModule + satisfies）。
 */

// ---------- 通用 ----------
export interface CTALink {
  label: string;
  href: string;
  /** primary=实心主按钮，secondary=描边按钮，text=文字链接 */
  variant: 'primary' | 'secondary' | 'text';
}

export interface NavItem {
  label: string;
  href: string;
  /** 徽标，如 "New" */
  badge?: string;
  children?: { label: string; href: string; description?: string }[];
}

// ---------- 站点级（导航/页脚） ----------
export interface SiteContent {
  brand: { name: string; logoText: string };
  nav: NavItem[];
  actions: { login: CTALink; primary: CTALink };
  footer: {
    about: string;
    columns: { title: string; links: { label: string; href: string }[] }[];
    agreements: { label: string; href: string }[];
    icp: string;
    copyright: string;
  };
}

// ---------- 首页 ----------
export interface LogoItem {
  name: string;
  /** 纯文本 Logo（避免外链图片失效，可用首字母 + 名称渲染） */
  text: string;
}

export interface ScenarioItem {
  title: string;
  description: string;
  /** 图标名，映射 components/icons.tsx 中的内联 SVG */
  icon: string;
}

export interface FeatureTab {
  key: string;
  label: string;
  title: string;
  description: string;
  bullets: string[];
  cta: CTALink;
  icon: string;
}

export interface SecurityItem {
  title: string;
  description: string;
}

export interface OpenSourceItem {
  name: string;
  description: string;
  stars: string;
  href: string;
}

export interface HomeContent {
  hero: {
    title: string;
    titleHighlight: string;
    subtitle: string;
    ctas: CTALink[];
  };
  logoWall: { title: string; note: string; logos: LogoItem[] };
  scenarios: { title: string; subtitle: string; items: ScenarioItem[] };
  superAssistant: {
    badge: string;
    title: string;
    titleHighlight: string;
    description: string;
    ctas: CTALink[];
    docLink: CTALink;
    stats: { value: string; label: string }[];
  };
  featureTabs: { title: string; subtitle: string; tabs: FeatureTab[] };
  security: { title: string; subtitle: string; items: SecurityItem[] };
  openSource: { title: string; subtitle: string; items: OpenSourceItem[] };
  about: {
    title: string;
    paragraphs: string[];
    vision: string;
    teamNote: string;
  };
}

// ---------- 产品门户页 ----------
export interface PortalContent {
  hero: {
    badge: string;
    title: string;
    titleHighlight: string;
    subtitle: string;
    ctas: CTALink[];
  };
  toolchain: {
    title: string;
    subtitle: string;
    items: { title: string; description: string; icon: string }[];
  };
  highlights: { title: string; description: string; icon: string }[];
}

// ---------- 超级助理产品页 ----------
export interface AgentPageContent {
  hero: HomeContent['superAssistant'];
  capabilities: { title: string; description: string; icon: string }[];
  sections: { title: string; subtitle: string; bullets: string[] }[];
}

// ---------- 定价页 ----------
export interface Plan {
  key: string;
  name: string;
  /** 价格展示文本，如 "¥0/年" */
  price: string;
  /** 原价（划线），可选 */
  originalPrice?: string;
  /** 角标，如 "限时特惠" */
  badge?: string;
  billingOptions?: { label: string; note?: string }[];
  cta: CTALink;
  tagline: string;
}

/** 对比表一行；四个值对应基础/标准/专业/企业，null 表示 ✗，字符串为展示文本 */
export interface CompareRow {
  feature: string;
  values: (string | null)[];
  /** 该行是否分组标题行 */
  group?: string;
}

export interface CreditPack {
  points: string;
  price: string;
  tagline: string;
  badge?: string;
}

export interface PricingContent {
  hero: { title: string; subtitle: string };
  planTabs: { upgrade: string; credits: string };
  plans: Plan[];
  compare: { title: string; rows: CompareRow[] };
  credits: {
    title: string;
    subtitle: string;
    packs: CreditPack[];
    freeNote: string;
  };
  consultation: { label: string; href: string };
}

// ---------- 404 ----------
export interface NotFoundContent {
  title: string;
  description: string;
  primaryCta: CTALink;
  secondaryCta: CTALink;
}
