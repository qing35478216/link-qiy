/**
 * console-instance —— 控制台 axios 实例（sdk-ts 生成客户端的载体）。
 * - baseURL 可配（VITE_API_BASE_URL）
 * - 请求拦截器：注入 Authorization + X-Tenant-Id（resp.headers['x-tenant-id'] 回传值）
 * - 响应拦截器：从登录/刷新响应捕获 x-tenant-id；401 时尝试刷新令牌并重放原请求一次
 */
import axios from 'axios';
import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { tokenStore } from './token-store';

export const consoleAxios: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
});

// 测试环境（MSW node server）走 fetch adapter，浏览器开发/生产走默认 xhr
if (import.meta.env.MODE === 'test') {
  consoleAxios.defaults.adapter = 'fetch';
}

const TENANT_HEADER = 'x-tenant-id';
const AUTH_PATHS = ['/auth/phone/login', '/auth/refresh'];

consoleAxios.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const accessToken = tokenStore.getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  const tenantId = tokenStore.getTenantId();
  if (tenantId) {
    config.headers[TENANT_HEADER] = tenantId;
  }
  return config;
});

function isAuthPath(url: string | undefined): boolean {
  return AUTH_PATHS.some((path) => url?.includes(path));
}

/** 401 刷新 + 重放：避免并发刷新，失败则清登录态 */
let refreshing: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStore.getRefreshToken();
  if (!refreshToken) {
    throw new Error('no refresh token');
  }
  const response = await consoleAxios.post<{ accessToken: string; refreshToken: string }>(
    '/auth/refresh',
    { refreshToken },
  );
  const { accessToken, refreshToken: nextRefresh } = response.data;
  tokenStore.setTokens(accessToken, nextRefresh);
  const tenantId = response.headers[TENANT_HEADER];
  if (typeof tenantId === 'string' && tenantId) {
    tokenStore.setTenantId(tenantId);
  }
  return accessToken;
}

consoleAxios.interceptors.response.use(
  (response) => {
    // 登录/刷新响应回传租户 ID（契约：网关从 JWT 解析注入）
    if (isAuthPath(response.config.url)) {
      const tenantId = response.headers[TENANT_HEADER];
      if (typeof tenantId === 'string' && tenantId) {
        tokenStore.setTenantId(tenantId);
      }
    }
    return response;
  },
  async (error: AxiosError) => {
    const config = error.config;
    const isUnauthorized = error.response?.status === 401;
    const alreadyRetried = config?.headers?.['x-retry-once'] === '1';
    if (!isUnauthorized || !config || isAuthPath(config.url) || alreadyRetried) {
      if (isUnauthorized && !tokenStore.getAccessToken()) {
        tokenStore.clear();
      }
      return Promise.reject(error);
    }
    try {
      refreshing ??= refreshAccessToken();
      const accessToken = await refreshing;
      config.headers['x-retry-once'] = '1';
      config.headers.Authorization = `Bearer ${accessToken}`;
      return consoleAxios.request(config);
    } catch {
      tokenStore.clear();
      return Promise.reject(error);
    } finally {
      refreshing = null;
    }
  },
);
