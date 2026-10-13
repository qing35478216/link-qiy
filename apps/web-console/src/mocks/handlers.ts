/**
 * mocks/handlers —— 组合 sdk-ts 生成的 MSW handlers + 内存夹具。
 * 铁律：路由 handlers 一律来自 @linkai/sdk-ts/msw/* 生成物；本文件只做夹具注入。
 * 注：Phase 0 不模拟 404 边界（列表→配置链路中 id 恒存在）。
 */
import type { RequestHandler } from 'msw';
import {
  getListAppsMockHandler,
  getCreateAppMockHandler,
  getGetAppMockHandler,
  getUpdateAppMockHandler,
  getDeleteAppMockHandler,
  getGetAppConfigMockHandler,
  getPutAppConfigMockHandler,
  getGetMyProfileMockHandler,
  getUpdateMyProfileMockHandler,
  getGetQuotaSummaryMockHandler,
  getLoginByPhoneMockHandler,
  getSendSmsCodeMockHandler,
  getRefreshTokenMockHandler,
  getLogoutMockHandler,
} from '@linkai/sdk-ts/msw/console';
import { getListModelsMockHandler } from '@linkai/sdk-ts/msw/service';
import type { App, AppConfig, UserProfile } from '@linkai/sdk-ts/console';
import { MOCK_TENANT_ID, createMockApp, getMockState, paginateApps } from './fixtures';

/**
 * 登录/刷新响应回传 X-Tenant-Id（契约：网关从 JWT 解析注入，前端透传）。
 * 生成 handler 只控制 body，租户头由此中间件补齐。
 */
const tenantHeaderMiddleware: RequestHandler = async ({ request }, next) => {
  const response = await next();
  if (request.url.includes('/auth/')) {
    response.headers.set('x-tenant-id', MOCK_TENANT_ID);
  }
  return response;
};

function findApp(appId: string): App {
  return (
    getMockState().apps.find((item) => item.id === appId) ?? {
      name: '应用不存在或已删除',
      type: 'lightweight',
    }
  );
}

export const handlers: RequestHandler[] = [
  // 中间件置首：包裹其后所有路由 handler
  tenantHeaderMiddleware,

  getLoginByPhoneMockHandler({
    accessToken: 'mock-access-token',
    refreshToken: 'mock-refresh-token',
    expiresIn: 7200,
    tokenType: 'Bearer',
  }),
  getRefreshTokenMockHandler({
    accessToken: 'mock-access-token-refreshed',
    refreshToken: 'mock-refresh-token-refreshed',
    expiresIn: 7200,
    tokenType: 'Bearer',
  }),
  getSendSmsCodeMockHandler(),
  getLogoutMockHandler(),
  getGetMyProfileMockHandler(() => getMockState().profile),
  getUpdateMyProfileMockHandler(({ request }) => {
    const patch = request.body as Partial<UserProfile>;
    Object.assign(getMockState().profile, patch);
    return getMockState().profile;
  }),
  getGetQuotaSummaryMockHandler(() => getMockState().quota),

  getListAppsMockHandler(({ request }) => {
    const url = new URL(request.url);
    const type = url.searchParams.get('type') ?? 'all';
    const limit = Number(url.searchParams.get('limit') ?? '12');
    const cursor = url.searchParams.get('cursor');
    const { items, nextCursor } = paginateApps(cursor, limit);
    const filtered = type === 'all' ? items : items.filter((app) => app.type === type);
    return { items: filtered, nextCursor };
  }),

  getCreateAppMockHandler(async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      description?: string;
      type: 'lightweight' | 'knowledge';
    };
    return createMockApp(body);
  }),

  getGetAppMockHandler(({ params }) => findApp(String(params.appId))),

  getUpdateAppMockHandler(async ({ params, request }) => {
    const appId = String(params.appId);
    const patch = (await request.json()) as Partial<App>;
    const app = getMockState().apps.find((item) => item.id === appId);
    if (!app) return findApp(appId);
    Object.assign(app, patch, { updatedAt: new Date().toISOString() });
    return app;
  }),

  getDeleteAppMockHandler(({ params }) => {
    const appId = String(params.appId);
    const state = getMockState();
    state.apps = state.apps.filter((item) => item.id !== appId);
    delete state.configs[appId];
    return undefined;
  }),

  getGetAppConfigMockHandler(({ params }) => {
    const appId = String(params.appId);
    return structuredClone(getMockState().configs[appId] ?? {});
  }),

  getPutAppConfigMockHandler(async ({ params, request }) => {
    const appId = String(params.appId);
    const next = (await request.json()) as AppConfig;
    const state = getMockState();
    state.configs[appId] = next;
    const app = state.apps.find((item) => item.id === appId);
    if (app) {
      app.currentVersion = (app.currentVersion ?? 0) + 1;
      app.updatedAt = new Date().toISOString();
    }
    return { version: app?.currentVersion ?? 1 };
  }),

  getListModelsMockHandler(() => ({
    data: [
      {
        code: 'gpt-4o',
        name: 'GPT-4o',
        provider: 'OpenAI',
        capabilities: ['chat', 'vision'],
        contextLength: 128000,
        price: { inputPer1k: 0.005, outputPer1k: 0.015 },
        enabled: true,
      },
      {
        code: 'gpt-4o-mini',
        name: 'GPT-4o mini',
        provider: 'OpenAI',
        capabilities: ['chat'],
        contextLength: 128000,
        price: { creditPerCall: 2 },
        enabled: true,
      },
      {
        code: 'claude-sonnet',
        name: 'Claude Sonnet',
        provider: 'Anthropic',
        capabilities: ['chat', 'reasoning'],
        contextLength: 200000,
        price: { inputPer1k: 0.003, outputPer1k: 0.015 },
        enabled: true,
      },
    ],
  })),
];
