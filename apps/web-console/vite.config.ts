import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';

/**
 * apps/web-console —— Vue3 + TS + Element Plus + Pinia + TanStack Query。
 * workspace 源码包（sdk-ts / ui）经 alias 直消费源码，保证类型与构建同源。
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 注：sdk-ts 包 exports 的 "." 指向尚不存在的 src/index.ts（已上报），
      // 现阶段经子路径消费生成物：console / service / models / msw。
      // 路径以本文件（apps/web-console/）为基准，packages/ 在 ../../ —— 少一级会解析到不存在的 apps/packages/。
      '@linkai/sdk-ts/console': fileURLToPath(
        new URL('../../packages/sdk-ts/src/console.ts', import.meta.url),
      ),
      // console.ts/service.ts 未 re-export models（SDK 打包缺口，已上报）；
      // 契约模型类型经 models 子路径直消费生成物
      '@linkai/sdk-ts/models/console': fileURLToPath(
        new URL('../../packages/sdk-ts/src/models/console/index.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/models/service': fileURLToPath(
        new URL('../../packages/sdk-ts/src/models/service/index.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/service': fileURLToPath(
        new URL('../../packages/sdk-ts/src/service.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/msw/console': fileURLToPath(
        new URL('../../packages/sdk-ts/src/console.msw.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/msw/service': fileURLToPath(
        new URL('../../packages/sdk-ts/src/service.msw.ts', import.meta.url),
      ),
      '@linkai/ui': fileURLToPath(new URL('../../packages/ui/src/index.ts', import.meta.url)),
      '@linkai/ui/tokens.css': fileURLToPath(
        new URL('../../packages/ui/src/styles/tokens.css', import.meta.url),
      ),
    },
  },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          // 首屏预算：框架与 UI 库单独成 chunk，业务代码按路由懒加载
          vue: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus'],
          query: ['@tanstack/vue-query'],
        },
      },
    },
  },
});
