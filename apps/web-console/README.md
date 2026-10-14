# apps/web-console — Builder 控制台

Vue3 + TypeScript + Element Plus + Pinia + TanStack Query。feature-sliced 架构，API 层全部用 packages/sdk-ts 生成客户端。视觉基准：linkai-screenshots/。

领地：控制台前端工程师（frontend-console）+ 画布工程师（canvas-engineer，画布模块）。

## 快速开始

```bash
pnpm install
pnpm --filter @linkai/web-console dev        # 开发（默认开 MSW Mock）
pnpm --filter @linkai/web-console test       # vitest（jsdom + MSW node server）
pnpm --filter @linkai/web-console typecheck  # vue-tsc --noEmit
pnpm --filter @linkai/web-console lint       # ESLint strict
pnpm --filter @linkai/web-console build      # 生产构建（默认关 MSW）
```

环境变量见 `.env.example`（复制为 `.env`；`.env` 不入库）。

## MSW Mock

控制台在**无后端联调期**经 MSW（Mock Service Worker）跑内存夹具：`src/mocks/handlers.ts` 组合 `@linkai/sdk-ts/msw/*` 生成 handler + `src/mocks/fixtures.ts` 内存夹具（种子数据对齐 linkai-screenshots/ 实测截图）。

**开启规则**（`src/mocks/mock-enabled.ts`，安全默认）：

| 环境 | 默认 | 说明 |
|---|---|---|
| `vite dev` | 开 | 开发默认走 Mock |
| `vitest` | 开 | 测试经 MSW node server 拦截 |
| `vite build` / `vite preview` | **关** | 生产默认不注册 worker，防止夹具数据外泄 |
| 任意环境 + `VITE_ENABLE_MSW=true` | 开 | 逃生门：确需生产跑 Mock 时显式开启（需评估假数据暴露风险） |
| 任意环境 + `VITE_ENABLE_MSW=false` | 关 | 联调真实后端时显式关闭 |

**接真实后端**：`.env` 设 `VITE_API_BASE_URL=http://localhost:8080`（用户面 `VITE_SERVICE_API_BASE_URL`），并保持 `VITE_ENABLE_MSW=false` 或缺省；请求经 `src/api/console-instance.ts` 注入 `Authorization` 与 `X-Tenant-Id`。

**注意**：`fixtures.ts` 只是 Mock 数据（含 Mock token、任意 ≥4 位验证码即登录），**不构成契约**——契约以 `packages/contracts/openapi/*.yaml` 为准；Mock handler 与契约的偏差以契约为准同步修正。
