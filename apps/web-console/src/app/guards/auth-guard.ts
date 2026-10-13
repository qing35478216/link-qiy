/**
 * guards —— 权限守卫（注册式，便于测试）。
 * - 未登录访问受保护路由 → /login?redirect=原路径
 * - 已登录访问 /login → 回控制台首页
 * - 路由标题同步 document.title
 */
import type { Router } from 'vue-router';
import { useAuthStore } from '@/app/stores/auth-store';

export function registerAuthGuard(router: Router): void {
  router.beforeEach((to) => {
    const authStore = useAuthStore();
    authStore.restore();

    if (!to.meta.public && !authStore.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } };
    }
    if (to.name === 'login' && authStore.isAuthenticated) {
      return { path: '/console/factory' };
    }
    const title = typeof to.meta.title === 'string' ? to.meta.title : '';
    document.title = title ? `${title} · Link.AI 控制台` : 'Link.AI 控制台';
    return true;
  });
}
