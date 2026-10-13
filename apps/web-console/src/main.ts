import { createApp } from 'vue';
import { createPinia } from 'pinia';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import App from './App.vue';
import { router } from './app/router';
import { registerAuthGuard } from './app/guards/auth-guard';
import { vueQueryPlugin } from './app/providers/query-client';
import './app/styles/index.css';

registerAuthGuard(router);

async function bootstrap(): Promise<void> {
  // Phase 0：无后端联调期，默认经 MSW 跑 Mock（VITE_ENABLE_MSW=false 可关）
  if (import.meta.env.VITE_ENABLE_MSW !== 'false') {
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
