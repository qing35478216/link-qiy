import { defineConfig } from 'orval';

// sdk-ts 生成配置：console + service 双契约 → 类型 + axios 客户端 + MSW handlers
export default defineConfig({
  console: {
    input: {
      target: './openapi/console-api.yaml',
      // orval v8 默认禁止外部 $ref（防 SSRF/任意文件读取）。契约把公共模型抽到
      // schemas/common.yaml，这里显式放行；新增 schema 文件需同步登记。
      parserOptions: { externalRefs: { allow: ['../schemas/common.yaml'] } },
    },
    output: {
      target: '../sdk-ts/src/console.ts',
      schemas: '../sdk-ts/src/models/console',
      client: 'axios',
      // orval v8 起 mock 改为 generators 数组；沿用 v7 的 `mock: { type: 'msw' }` 会
      // 直接抛 "mock.generators must be an array of generator entries"。
      mock: { generators: [{ type: 'msw' }] }, // 前端 Mock 驱动开发的关键产物
      prettier: true,
    },
  },
  service: {
    input: {
      target: './openapi/service-api.yaml',
      parserOptions: { externalRefs: { allow: ['../schemas/common.yaml'] } },
    },
    output: {
      target: '../sdk-ts/src/service.ts',
      schemas: '../sdk-ts/src/models/service',
      client: 'axios',
      mock: { generators: [{ type: 'msw' }] },
      prettier: true,
    },
  },
});
