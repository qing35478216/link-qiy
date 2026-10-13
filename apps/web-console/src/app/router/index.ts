/**
 * router —— 控制台路由（懒加载 + 权限守卫）。
 * 结构：/login（免鉴权）→ /console（外壳布局，懒加载子路由）。
 */
import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import { NAV_GROUPS } from './nav-config';

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/features/auth/pages/LoginPage.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/console',
    component: () => import('@/app/layouts/ConsoleLayout.vue'),
    redirect: '/console/factory',
    children: [
      {
        path: 'factory',
        name: 'factory',
        component: () => import('@/features/app/pages/FactoryPage.vue'),
        meta: { title: '智能体', navKey: 'factory', breadcrumb: ['创造', '智能体'] },
      },
      {
        path: 'apps/:appId/config',
        name: 'app-config',
        component: () => import('@/features/app/pages/AppConfigPage.vue'),
        meta: { title: '应用配置', breadcrumb: ['创造', '智能体', '应用配置'] },
      },
      {
        path: 'apps/:appId/chat',
        name: 'app-chat',
        component: () => import('@/shared/pages/PlaceholderPage.vue'),
        meta: { title: '对话', breadcrumb: ['创造', '智能体', '对话'] },
      },
      ...NAV_GROUPS.flatMap((group) =>
        group.items
          .filter((item) => item.placeholder)
          .map((item) => ({
            path: item.route.replace('/console/', ''),
            name: item.key,
            component: () => import('@/shared/pages/PlaceholderPage.vue'),
            meta: {
              title: item.label,
              navKey: item.key,
              breadcrumb: [group.label, item.label],
            },
          })),
      ),
    ],
  },
  {
    path: '/',
    redirect: '/console/factory',
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/console/factory',
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});
