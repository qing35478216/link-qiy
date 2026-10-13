import { defineConfig } from 'orval';

// sdk-ts 生成配置：console + service 双契约 → 类型 + axios 客户端 + MSW handlers
export default defineConfig({
  console: {
    input: { target: './openapi/console-api.yaml' },
    output: {
      target: '../sdk-ts/src/console.ts',
      schemas: '../sdk-ts/src/models/console',
      client: 'axios',
      mock: { type: 'msw' }, // 前端 Mock 驱动开发的关键产物
      prettier: true,
    },
  },
  service: {
    input: { target: './openapi/service-api.yaml' },
    output: {
      target: '../sdk-ts/src/service.ts',
      schemas: '../sdk-ts/src/models/service',
      client: 'axios',
      mock: { type: 'msw' },
      prettier: true,
    },
  },
});
