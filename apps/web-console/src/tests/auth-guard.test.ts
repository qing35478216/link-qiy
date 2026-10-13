/**
 * 权限守卫测试：未登录跳登录页（带 redirect），已登录访问 /login 回控制台。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { createRouter, createWebHistory } from 'vue-router';
import { tokenStore } from '@/api';

function buildRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/login', name: 'login', component: { template: '<div>login</div>' }, meta: { public: true } },
      {
        path: '/console',
        component: { template: '<div>console</div>' },
        children: [
          { path: 'factory', name: 'factory', component: { template: '<div>factory</div>' } },
        ],
      },
    ],
  });
}

describe('auth guard', () => {
  beforeEach(() => {
    tokenStore.clear();
  });

  it('未登录访问受保护路由 → /login?redirect=原路径', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = buildRouter();
    const { useAuthStore } = await import('@/app/stores/auth-store');
    useAuthStore(pinia).restore();

    // 复刻 main.ts 的守卫注册顺序
    const { registerAuthGuard } = await import('@/app/guards/auth-guard');
    registerAuthGuard(router);

    await router.push('/console/factory');
    await router.isReady();
    expect(router.currentRoute.value.name).toBe('login');
    expect(router.currentRoute.value.query.redirect).toBe('/console/factory');
  });

  it('已登录访问 /login → 回 /console/factory', async () => {
    tokenStore.setTokens('token', 'refresh');
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = buildRouter();
    const { useAuthStore } = await import('@/app/stores/auth-store');
    useAuthStore(pinia).restore();
    const { registerAuthGuard } = await import('@/app/guards/auth-guard');
    registerAuthGuard(router);

    await router.push('/login');
    await router.isReady();
    expect(router.currentRoute.value.path).toBe('/console/factory');
  });
});
