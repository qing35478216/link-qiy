import { config } from '@vue/test-utils';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';

// Element Plus 组件 + 图标全局注册（测试环境）
config.global.plugins = [ElementPlus];
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  config.global.components[name] = component;
}

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
