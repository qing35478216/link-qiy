/**
 * @linkai/sdk-ts 统一入口（手写聚合层，src/ 下其余文件均为 orval 生成物禁止手改）
 *
 * 消费方式（标准路径）：
 *   import { getLinkAIConsoleAPI, getLinkAIServiceAPI, type App, type ChatCompletionRequest } from '@linkai/sdk-ts';
 *
 * 两种客户端工厂均由 orval 生成（console.ts / service.ts），此处聚合导出；
 *  models/console 与 models/service 两套类型无命名冲突（已校验），可安全同出口。
 * MSW handlers 不走本入口（仅测试环境需要，避免生产构建引入 faker/msw）：
 *   import { getCreateWechatQrcodeMockHandler } from '@linkai/sdk-ts/msw/console';
 */

// 管理面客户端（Console API，Bearer JWT + X-Tenant-Id）
export * from './console';

// 用户面客户端（Service API，OpenAI 兼容，API Key）
export * from './service';

// 两套模型类型（console 管理面 / service 用户面）
export * from './models/console';
export * from './models/service';
