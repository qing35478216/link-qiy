import { fileURLToPath } from 'node:url';
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

/**
 * 测试环境复用主构建的 plugins / resolve.alias —— 直接 mergeConfig(viteConfig)，
 * 不再重复抄写 alias 表。抄写会导致 workspace 路径修正时漏改（本次 T-011 的
 * ENOENT 根因就是 vite.config.ts 与 vitest.config.ts 各有一份 '../packages/'）。
 * MSW 走 node server + fetch adapter。
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.ts'],
      setupFiles: [fileURLToPath(new URL('./src/test-setup.ts', import.meta.url))],
      pool: 'forks',
      testTimeout: 20000,
    },
  }),
);
