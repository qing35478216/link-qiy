import { config } from '@vue/test-utils';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import { server } from './mocks/node';

config.global.plugins = [ElementPlus];
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  config.global.components[name] = component;
}

// 所有 API 测试经 MSW node server 拦截（fetch adapter）
server.listen({ onUnhandledRequest: 'error' });

import { afterEach, beforeEach } from 'vitest';
import { resetMockDb } from './mocks/fixtures';

beforeEach(() => {
  resetMockDb();
});

afterEach(() => {
  server.resetHandlers();
});

// jsdom 缺失 API 兜底
if (!('ResizeObserver' in globalThis)) {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
}

if (!globalThis.matchMedia) {
  globalThis.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof globalThis.matchMedia;
}
