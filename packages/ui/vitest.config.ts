import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.test.ts'],
    setupFiles: ['./src/test-setup.ts'],
    // threads + 单线程：forks 池在本机内存受限环境下不稳定（进程被杀）
    pool: 'threads',
    poolOptions: {
      threads: { singleThread: true },
    },
    // element-plus / icons 源码数千小文件，直接 ESM 加载极慢；esbuild 预打包后大幅加速
    deps: {
      optimizer: {
        web: {
          enabled: true,
          include: ['element-plus', '@element-plus/icons-vue'],
        },
      },
    },
    testTimeout: 20000,
  },
});
