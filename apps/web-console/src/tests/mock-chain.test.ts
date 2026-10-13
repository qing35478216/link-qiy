/**
 * Mock 联调链路（契约 v0.1.1 + sdk-ts 生成客户端 + MSW）：
 * 登录态 → 应用列表（cursor 分页）→ 创建应用 → 读取配置 → 保存配置。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { server } from '@/mocks/node';
import { consoleAPI, tokenStore } from '@/api';
import { fetchAppsPage, createApp, fetchAppConfig, saveAppConfig } from '@/features/app/api/app-api';

describe('Mock 联调：登录态→列表→创建→配置保存', () => {
  beforeEach(() => {
    tokenStore.clear();
  });

  it('手机号登录：写入令牌并从响应头捕获租户 ID', async () => {
    const response = await consoleAPI.loginByPhone({
      phone: '13800008888',
      smsCode: '1234',
      agreementAccepted: true,
    });
    expect(response.status).toBe(200);
    expect(response.data.accessToken).toBe('mock-access-token');
    expect(response.headers['x-tenant-id']).toBe('tenant-demo-0001');
  });

  it('请求拦截器注入 Authorization 与 X-Tenant-Id', async () => {
    const login = await consoleAPI.loginByPhone({
      phone: '13800008888',
      smsCode: '1234',
      agreementAccepted: true,
    });
    tokenStore.setTokens(login.data.accessToken, login.data.refreshToken);
    tokenStore.setTenantId(String(login.headers['x-tenant-id']));

    let seenAuth = '';
    let seenTenant = '';
    server.events.on('request:start', ({ request }) => {
      seenAuth = request.headers.get('authorization') ?? '';
      seenTenant = request.headers.get('x-tenant-id') ?? '';
    });
    const page = await fetchAppsPage({ limit: 2 });
    server.events.removeAllListeners('request:start');

    expect(seenAuth).toBe('Bearer mock-access-token');
    expect(seenTenant).toBe('tenant-demo-0001');
    expect(page.items).toHaveLength(2);
    expect(page.nextCursor).toBe('2');
  });

  it('cursor 分页：翻页后不重复', async () => {
    const first = await fetchAppsPage({ limit: 2 });
    const second = await fetchAppsPage({ limit: 2, cursor: first.nextCursor ?? undefined });
    expect(first.items.map((app) => app.id)).not.toEqual(second.items.map((app) => app.id));
    expect(second.nextCursor).toBeNull();
  });

  it('创建应用后出现在列表，且可直接读取/保存配置', async () => {
    const created = await createApp({ name: '梅花易数', description: '测试创建', type: 'lightweight' });
    expect(created.id).toBeTruthy();

    const page = await fetchAppsPage({ limit: 50 });
    expect(page.items.some((app) => app.id === created.id)).toBe(true);

    const config = await fetchAppConfig(created.id!);
    expect(config.modelPrompt?.modelCode).toBe('gpt-4o');

    config.modelPrompt = { ...config.modelPrompt, systemPrompt: '新的系统提示词' };
    const version = await saveAppConfig(created.id!, config);
    expect(version).toBeGreaterThan(0);

    const reloaded = await fetchAppConfig(created.id!);
    expect(reloaded.modelPrompt?.systemPrompt).toBe('新的系统提示词');
  });

  it('配额摘要：版本徽标 + 用量', async () => {
    const quota = (await consoleAPI.getQuotaSummary()).data;
    expect(quota.planBadge).toBe('基础版');
    expect(quota.walletBalance).toBe(40240);
    expect(quota.usage?.messagesLimit).toBe(500);
  });
});
