# apps/web-marketing — 营销站群

Next.js 14 SSG（App Router + Tailwind，output: export）。官网首页 / 产品门户 / 超级助理产品页 / 定价页 / 404。内容全部 CMS 化配置（`content/*.json`）。Lighthouse ≥95（实测 100×4）。

领地：营销站与 SDK 工程师（marketing-sdk）。

## 命令

```bash
pnpm dev        # 本地开发
pnpm build      # SSG 构建 → out/（纯静态产物）
pnpm lint       # eslint-config-next
pnpm typecheck  # tsc --noEmit（含 content/*.json 结构校验）
node scripts/serve-out.mjs 8899   # 本地预览 out/（预压缩，对齐 CDN）
```

## 内容 CMS 化

- 内容数据：`content/site.json`（导航/页脚）、`home.json`（首页九模块）、`portal.json`、`agent.json`、`pricing.json`（Mock）、`not-found.json`
- 类型定义：`lib/content.ts`；改内容只动 JSON，组件零改动
- 契约冻结后定价数据源替换方式见 `ADOPTED-TOOLS.md`

## 页面与 SEO

- `/` 首页（Hero/Logo 墙/场景轮播/超级助理/9 Tab/安全合规/开源墙/关于我们）、`/portal`、`/agent`、`/price`、`/agreement`、`/privacy`、404
- 全部响应式 + 暗色模式（class 策略 + 内联初始化脚本防 FOUC）
- metadata / OpenGraph / sitemap.ts / robots.ts / Organization + Product JSON-LD
