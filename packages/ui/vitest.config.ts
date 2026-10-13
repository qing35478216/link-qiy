import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test-setup.ts'],
    // threads + 单线程：forks 池在本机内存受限环境下不稳定（el-table 渲染/进程被杀），线程池更稳
    pool: 'threads',
    poolOptions: {
      threads: { singleThread: true },
    },
  },
});
