/**
 * mocks/handlers —— 组合 sdk-ts 生成的 MSW handlers + 内存夹具。
 * 铁律：路由 handlers 一律来自 @linkai/sdk-ts/msw/* 生成物；本文件只做夹具注入。
 * 注：Phase 0 不模拟 404 边界（列表→配置链路中 id 恒存在）。
 */
import type { RequestHandler } from 'msw';
import { http, HttpResponse } from 'msw';
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
  getSendSmsCodeMockHandler,
  getLogoutMockHandler,
} from '@linkai/sdk-ts/msw/console';
import { getListModelsMockHandler } from '@linkai/sdk-ts/msw/service';
import type { App, AppConfig, UserProfile } from '@linkai/sdk-ts/models/console';
import { MOCK_TENANT_ID, createMockApp, getMockState, paginateApps } from './fixtures';

/**
 * 登录/刷新响应回传 X-Tenant-Id（契约：网关从 JWT 解析注入，前端透传）。
 * 说明：生成 handler 只能控制响应体，无法设置响应头；这两个 auth 路由
 * 因此用手写 handler 模拟网关的租户头注入（Mock 层适配，非契约变更）。
 * 其余路由一律使用 @linkai/sdk-ts/msw/* 生成 handler。
 */
function authResponseWithTenant(body: Record<string, unknown>): Response {
  // msw 的 JsonBodyType 不接受任意 Record，登录/刷新响应体形状在此收窄一次
  const response = HttpResponse.json(body as Record<string, string | number>);
  response.headers.set('x-tenant-id', MOCK_TENANT_ID);
  return response;
}

const loginMockHandler = http.post('*/auth/phone/login', async ({ request }) => {
  const payload = (await request.json()) as { phone: string; smsCode: string };
  if (payload.smsCode.length < 4) {
    return HttpResponse.json({ message: '验证码错误' }, { status: 403 });
  }
  return authResponseWithTenant({
    accessToken: 'mock-access-token',
    refreshToken: 'mock-refresh-token',
    expiresIn: 7200,
    tokenType: 'Bearer',
  });
});

const refreshMockHandler = http.post('*/auth/refresh', async ({ request }) => {
  const payload = (await request.json()) as { refreshToken: string };
  if (!payload.refreshToken) {
    return HttpResponse.json({ message: 'refresh token 缺失' }, { status: 401 });
  }
  return authResponseWithTenant({
    accessToken: 'mock-access-token-refreshed',
    refreshToken: 'mock-refresh-token-refreshed',
    expiresIn: 7200,
    tokenType: 'Bearer',
  });
});

function findApp(appId: string): App {
  return (
    getMockState().apps.find((item) => item.id === appId) ?? {
      name: '应用不存在或已删除',
      type: 'lightweight',
    }
  );
}

export const handlers: RequestHandler[] = [
  // auth 路由：手写 handler 注入 x-tenant-id（生成 handler 无法设置响应头）
  loginMockHandler,
  refreshMockHandler,

  getSendSmsCodeMockHandler(),
  getLogoutMockHandler(),
  getGetMyProfileMockHandler(() => getMockState().profile),
  getUpdateMyProfileMockHandler(async ({ request }) => {
    const patch = (await request.json()) as Partial<UserProfile>;
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
    // Page.items 为通用 object 数组；展开为对象字面量以贴合索引签名类型
    return { items: filtered.map((app) => ({ ...app })), nextCursor };
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
    const version = (app?.currentVersion ?? 0) + 1;
    // App.currentVersion/updatedAt 为契约 readOnly 字段：整体替换而非原地赋值
    state.apps = state.apps.map((item) =>
      item.id === appId ? { ...item, currentVersion: version, updatedAt: new Date().toISOString() } : item,
    );
    return { version };
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
