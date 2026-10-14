# packages/sdk-ts — 前端生成物

由契约生成：API 客户端 + TypeScript 类型 + MSW handlers。**src/ 下除 index.ts 外均为 orval 生成物，禁止手改**（前端工程师只消费；契约变更走 contract-engineer 重新生成）。

领地：契约工程师（生成）、前端工程师（只读使用）。

## 标准消费路径（T-011 起）

```ts
import { getLinkAIConsoleAPI, getLinkAIServiceAPIOpenAI } from '@linkai/sdk-ts';
import type { App, AppConfig, UserProfile } from '@linkai/sdk-ts';
```

- `getLinkAIConsoleAPI(axiosInstance?)` —— 管理面客户端工厂（console-api）：`getMyProfile / listApps / createApp / getApp / updateApp / deleteApp / getAppConfig / putAppConfig / publishApp / unpublishApp / listAppVersions / snapshotAppConfig / rollbackAppConfig / getQuotaSummary / 登录族`。默认用全局 axios 实例；**生产必须传入注入了 baseURL（网关 console 路由）、Authorization Bearer、X-Tenant-Id 的实例**。
- `getLinkAIServiceAPIOpenAI(axiosInstance?)` —— 用户面客户端工厂（service-api，OpenAI 兼容）：`createChatCompletion / listModels / listApiKeys / createApiKey / deleteApiKey`。鉴权用 API Key（Bearer）。
- MSW handlers（仅测试环境）：`import { getCreateWechatQrcodeMockHandler } from '@linkai/sdk-ts/msw/console'`（service 面对应 `/msw/service`）。两个入口文件导出全部 `getXxxMockHandler` 工厂，可直接展开进 `setupServer(...)`。
- 也可走细粒度入口：`@linkai/sdk-ts/console`、`@linkai/sdk-ts/service`、`@linkai/sdk-ts/models/console`、`@linkai/sdk-ts/models/service`。

## 两个已知消费侧注意（生成物特性，非缺陷）

1. **列表 items 是宽松索引签名**：`Page` 为通用分页 schema，`listApps` 等返回的 `items` 元素类型是 `{ [key: string]: unknown }`，消费侧按需断言：`const app = page.items?.[0] as App | undefined`。
2. **createChatCompletion 返回联合类型**：契约中 200 同时声明 `application/json` 与 `text/event-stream`，生成类型为 `ChatCompletionResponse | string`——`stream: false` 时 narrowing：`if (typeof data !== 'string') { ... }`。

## 验证

```bash
pnpm --filter @linkai/sdk-ts typecheck   # tsc --noEmit（strict + noUncheckedIndexedAccess）
```

已验证：`import { getLinkAIConsoleAPI, type App } from '@linkai/sdk-ts'` 标准路径编译通过（T-016 修复单验证记录）。
