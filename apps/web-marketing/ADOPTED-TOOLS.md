# ADOPTED-TOOLS — apps/web-marketing 选型记录（铁律 8）

> 选型核查四项：维护活跃度 / Issue 响应 / 许可证 / 技术栈匹配。结论均基于 2026-10 检索。

## 依赖清单（全部 pinned）

| 库 | 版本 | License | 引入理由 |
|---|---|---|---|
| next | 14.2.35 | MIT | 工单指定技术栈（docs/02 §6.2：Next.js 14 + Tailwind）；App Router SSG |
| react / react-dom | 18.3.1 | MIT | Next 14 配套 |
| tailwindcss / postcss / autoprefixer | 3.4.17 / 8.4.49 / 10.4.20 | MIT | 工单指定；utility-first，暗色模式走 `dark:` class |
| eslint / eslint-config-next | 8.57.1 / 14.2.35 | MIT | 工程规范（ESLint strict） |
| typescript | 5.7.2 | Apache-2.0 | 构建期校验 CMS JSON 结构 |
| vitepress（apps/docs） | 1.5.0 | MIT | 工单指定文档站方案 |

无运行时第三方依赖；无 UI 组件库、无图标库、无暗色切换库（见下）。

## 选型对比

### 1. 内容方案：contentlayer vs 纯 JSON（`content/*.json` + TS interfaces）

| 方案 | 活跃度 | 许可证 | 结论 |
|---|---|---|---|
| contentlayer | ❌ GitHub 归档（2023 停更，官方声明 "sunset"，Next 14 兼容靠社区补丁） | MIT | 否决：主仓库 archived，近 3 年无提交，不满足核查项① |
| Fuma Contentlayer (fumadocs) | ✅ 活跃（fumadocs 持续发版） | MIT | 候选，但引入整套路由/渲染体系，营销站 4 页场景过重 |
| **纯 JSON + TS interfaces** | — | — | **采纳**：零依赖；`resolveJsonModule` 使 JSON 在构建期获得完整类型检查；运营改 JSON 不改代码即满足 CMS 诉求；数据结构由 `lib/content.ts` 单一定义 |

### 2. UI 方案：Tailwind 插件/UI 库 vs 手写 utility

| 方案 | 结论 |
|---|---|
| shadcn/ui | 否决：React Server Component 体系优秀但组件量远超 4 页营销站需求，增加维护面 |
| daisyUI / Flowbite | 否决：暗色语义覆盖与自定义设计令牌冲突，样式覆写成本高于收益 |
| **Tailwind utility + 少量 `@layer components` 语义类**（`.btn-primary` / `.card` / `.section-title`） | **采纳**：零组件库依赖，设计令牌走 CSS 变量（`--bg/--border/--text`），暗色仅覆盖变量 |

### 3. 图标：lucide-react vs 内联 SVG

| 方案 | 结论 |
|---|---|
| lucide-react（MIT，活跃，tree-shaking 良好） | 候选合理，但营销站图标仅 ~25 个且需品牌定制 |
| **components/icons.tsx 内联 SVG** | **采纳**：零依赖、零运行时成本、单文件可审计；名称映射由 CMS JSON 的 `icon` 字段驱动 |

### 4. 暗色模式：next-themes vs 内联脚本

| 方案 | 结论 |
|---|---|
| next-themes（MIT，~1.6KB，活跃） | 成熟可靠；但本站点仅一个 theme toggle |
| **layout 内联初始化脚本 + 32 行 ThemeToggle** | **采纳**：SSG 产物无 hydration 闪动（FOUC），零依赖，逻辑全可见 |

### 5. 轮播/Tab 组件：自研 vs swiper/embla

| 方案 | 结论 |
|---|---|
| swiper（GPL → 商业需付费，排除）/ embla-carousel（MIT，活跃） | embla 为合理候选，但场景轮播逻辑仅 30 行（定时翻页 + 指示器） |
| **自研 ScenarioCarousel / FeatureTabs / PricingTabs** | **采纳**：交互极简，自研体积与心智成本均低于引入库；理由符合铁律 8 自研豁免条款（现有库满足需求但体积/复杂度大于收益） |

## 契约冻结后的数据源替换说明

定价数据当前为 Mock（`content/pricing.json`，数据取自 docs/01 §十 实测）。契约 `console-api.yaml`（T-001）冻结后：
1. `app/price/page.tsx` 改为 `async` 组件，`generateStaticParams`/构建期 fetch 定价接口（SSG 时数据内联进 HTML，不影响纯静态输出）；
2. JSON 降级为兜底默认值；组件结构零改动（Props 即 `PricingContent`）。

## 验证方式（T-009 交付实测）

- `next build`（output: export）通过：11 条路由全部 `○ (Static)`，`out/` 1.2MB 纯静态产物（含 sitemap.xml / robots.txt / 404.html）；
- `next lint`（eslint-config-next）与 `tsc --noEmit` 全过；
- **Lighthouse：首页 / 定价页 均 100 / 100 / 100 / 100**（Performance / Accessibility / Best Practices / SEO，headless Chrome 实测，见 commit dcc7be0）；
- Bundle 体积：First Load JS 共享 87.4 kB（框架 53.6 + 运行时 31.9 + 其它 1.9），首页整页 First Load 105 kB；CSS 单文件 15.6 kB（gzip 4.2 kB）；无外部图片/字体请求（图标全部内联 SVG），LCP 元素为纯文本；
- CMS 模块化验证：仅改 `content/home.json` 一行副标题 → 重建 → `out/index.html` 出现该文案，`components/` `app/` `lib/` 零 diff（用例已执行后还原）；
- 响应式：390px / 1440px 双断截图过检；暗色模式 `prefers-color-scheme` + 手动切换均验证（截图见交付说明）。

## 工程环境备注（非代码问题）

- 本机 WorkBuddy FS broker 偶发对 `next build` 的 `.next` 并发 mkdir / trace 收集报 EEXIST / ENOENT（重试即过）；CI 环境不受影响。
- 本地预览 `out/` 用 `node scripts/serve-out.mjs 8899`（预压缩，对齐 CDN 行为）。

