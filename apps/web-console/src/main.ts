import { createApp } from 'vue';
import { createPinia } from 'pinia';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import App from './App.vue';
import { router } from './app/router';
import { registerAuthGuard } from './app/guards/auth-guard';
import { vueQueryPlugin } from './app/providers/query-client';
import { isMockEnabled } from './mocks/mock-enabled';
import './app/styles/index.css';

registerAuthGuard(router);

async function bootstrap(): Promise<void> {
  // MSW 仅默认在开发/测试环境开启；生产构建默认关闭，防止 Mock 夹具数据外泄
  // （安全默认；确需生产开 Mock 显式设 VITE_ENABLE_MSW=true，见 mocks/mock-enabled.ts）
  if (isMockEnabled()) {
    const { startMockWorker } = await import('./mocks/browser');
    await startMockWorker();
  }

  const app = createApp(App);
  app.use(createPinia());
  app.use(ElementPlus);
  for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(name, component);
  }
  app.use(vueQueryPlugin[0], vueQueryPlugin[1]);
  app.use(router);
  app.mount('#app');
}

void bootstrap();
