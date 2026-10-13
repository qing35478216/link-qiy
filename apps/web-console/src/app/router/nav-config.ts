/**
 * nav-config —— 侧边栏四组导航（视觉基准：linkai-screenshots/01-factory）。
 * 与路由表同源：navKey 对应 route name。
 */
export interface NavItem {
  key: string;
  label: string;
  route: string;
  /** Phase 0 占位页（后续工单落地为独立 feature） */
  placeholder?: boolean;
}

export interface NavGroup {
  key: string;
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'create',
    label: '创造',
    items: [
      { key: 'factory', label: '智能体', route: '/console/factory' },
      { key: 'knowledge', label: '知识库', route: '/console/knowledge', placeholder: true },
      { key: 'database', label: '数据库', route: '/console/database', placeholder: true },
      { key: 'plugins', label: '插件', route: '/console/plugins', placeholder: true },
      { key: 'workflow', label: '工作流', route: '/console/workflow', placeholder: true },
    ],
  },
  {
    key: 'integration',
    label: '接入',
    items: [
      { key: 'channels', label: '渠道接入', route: '/console/channels', placeholder: true },
      { key: 'clients', label: '客户端', route: '/console/clients', placeholder: true },
      { key: 'conversations', label: '对话管理', route: '/console/conversations', placeholder: true },
    ],
  },
  {
    key: 'manage',
    label: '管理',
    items: [
      { key: 'account', label: '我的账户', route: '/console/account', placeholder: true },
      { key: 'models', label: '模型服务', route: '/console/models', placeholder: true },
      { key: 'dashboard', label: '数据看板', route: '/console/dashboard', placeholder: true },
      { key: 'team', label: '团队空间', route: '/console/team', placeholder: true },
    ],
  },
  {
    key: 'docs',
    label: '文档',
    items: [{ key: 'docs', label: '帮助文档', route: '/console/docs', placeholder: true }],
  },
];
