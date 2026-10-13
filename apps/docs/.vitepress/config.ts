import { defineConfig } from 'vitepress';

/**
 * 文档站配置。
 * 目录树：仓库 docs/（设计文档，sync 脚本同步）+ 本站原创文档（快速开始/SDK/API）。
 * llms.txt 由 scripts/gen-llms.mjs 在 build 后生成。
 */
export default defineConfig({
  lang: 'zh-CN',
  title: 'LinkAI 文档中心',
  description: 'LinkAI 一站式 AI 智能体平台官方文档',
  cleanUrls: true,
  lastUpdated: true,

  head: [['link', { rel: 'icon', href: '/favicon.ico' }]],

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: '指南', link: '/guide/getting-started' },
      { text: '嵌入 SDK', link: '/sdk/embed' },
      { text: '开放 API', link: '/api/chat' },
      { text: '设计文档', link: '/design/overview' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: '指南',
          items: [{ text: '快速开始', link: '/guide/getting-started' }],
        },
      ],
      '/sdk/': [
        {
          text: '嵌入 SDK',
          items: [{ text: '网页嵌入', link: '/sdk/embed' }],
        },
      ],
      '/api/': [
        {
          text: '开放 API',
          items: [{ text: '对话接口', link: '/api/chat' }],
        },
      ],
      '/design/': [
        {
          text: '设计文档（仓库 docs/ 同步）',
          items: [
            { text: '总览', link: '/design/overview' },
            { text: '功能拆解蓝图', link: '/design/01-blueprint' },
            { text: '团队组建与实施方案', link: '/design/02-team-plan' },
            { text: '开发实现框架设计', link: '/design/03-architecture' },
            { text: '模块级实施规格', link: '/design/04-module-spec' },
            { text: 'AI 开发团队与提示词工程', link: '/design/05-ai-team' },
            { text: '工程踩坑记录', link: '/design/06-pitfalls' },
            { text: '可观测性', link: '/design/observability' },
          ],
        },
      ],
    },
    // socialLinks 暂缺：原配置指向 zhayujie/chatgpt-on-wechat（无关第三方仓库，疑似模板残留）。
    // 官方仓库地址需对照 link-ai.tech 实际信息核实后补充（邵宣恢复时处理）。
    footer: {
      message: 'LinkAI 文档中心',
      copyright: '© 2026 深圳极简未来科技有限公司',
    },
    search: { provider: 'local' },
  },
});
