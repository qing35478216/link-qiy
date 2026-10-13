import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';

/** 测试环境复用主构建的 alias；MSW 走 node server + fetch adapter */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@linkai/sdk-ts/console': fileURLToPath(
        new URL('../packages/sdk-ts/src/console.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/service': fileURLToPath(
        new URL('../packages/sdk-ts/src/service.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/msw/console': fileURLToPath(
        new URL('../packages/sdk-ts/src/console.msw.ts', import.meta.url),
      ),
      '@linkai/sdk-ts/msw/service': fileURLToPath(
        new URL('../packages/sdk-ts/src/service.msw.ts', import.meta.url),
      ),
      '@linkai/ui': fileURLToPath(new URL('../packages/ui/src/index.ts', import.meta.url)),
      '@linkai/ui/tokens.css': fileURLToPath(
        new URL('../packages/ui/src/styles/tokens.css', import.meta.url),
      ),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.ts'],
    setupFiles: ['./src/test-setup.ts'],
    deps: {
      optimizer: {
        web: {
          enabled: true,
          include: ['element-plus', '@element-plus/icons-vue'],
        },
      },
    },
    pool: 'forks',
    testTimeout: 20000,
  },
});
