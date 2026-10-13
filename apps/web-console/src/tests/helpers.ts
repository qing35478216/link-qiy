/**
 * 测试辅助：挂载组件时注入 Pinia / TanStack Query 提供者。
 */
import { mount } from '@vue/test-utils';
import type { Component } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query';

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
}

export function mountWithProviders(
  component: Component,
  options: Parameters<typeof mount>[1] = {},
): ReturnType<typeof mount> {
  const pinia = createPinia();
  setActivePinia(pinia);
  const queryClient = createTestQueryClient();
  return mount(component, {
    ...options,
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
      ...(options.global ?? {}),
    },
  });
}
