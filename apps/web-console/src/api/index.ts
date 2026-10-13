/**
 * api/ —— 契约客户端唯一入口（铁律：全部来自 @linkai/sdk-ts 生成物，零手写）。
 * console（管理面）与 service（用户面）分别绑定各自的 axios 实例。
 */
import axios from 'axios';
import type { AxiosInstance } from 'axios';
import { getLinkAIConsoleAPI } from '@linkai/sdk-ts/console';
import { getLinkAIServiceAPIOpenAI } from '@linkai/sdk-ts/service';
import { consoleAxios } from './console-instance';

export const consoleAPI = getLinkAIConsoleAPI(consoleAxios);

/** service 面（OpenAI 兼容）独立实例：用户 API Key 鉴权，不注入控制台租户头 */
export const serviceAxios: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_SERVICE_API_BASE_URL ?? '',
  timeout: 30000,
});

if (import.meta.env.MODE === 'test') {
  serviceAxios.defaults.adapter = 'fetch';
  serviceAxios.defaults.baseURL =
    import.meta.env.VITE_SERVICE_API_BASE_URL || 'http://localhost:5173';
}

export const serviceAPI = getLinkAIServiceAPIOpenAI(serviceAxios);

export { consoleAxios } from './console-instance';
export { tokenStore } from './token-store';
