/**
 * token-store —— 登录态持久化（纯函数，无框架依赖）。
 * 契约约定：X-Tenant-Id 由网关从 JWT 解析后经响应头回传，前端透传。
 */

const ACCESS_TOKEN_KEY = 'linkai.accessToken';
const REFRESH_TOKEN_KEY = 'linkai.refreshToken';
const TENANT_ID_KEY = 'linkai.tenantId';

function read(key: string): string | null {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) {
      globalThis.localStorage?.removeItem(key);
    } else {
      globalThis.localStorage?.setItem(key, value);
    }
  } catch {
    // 隐私模式等场景下静默降级为内存态
  }
}

export const tokenStore = {
  getAccessToken: (): string | null => read(ACCESS_TOKEN_KEY),
  getRefreshToken: (): string | null => read(REFRESH_TOKEN_KEY),
  getTenantId: (): string | null => read(TENANT_ID_KEY),
  setTokens(accessToken: string, refreshToken: string): void {
    write(ACCESS_TOKEN_KEY, accessToken);
    write(REFRESH_TOKEN_KEY, refreshToken);
  },
  setTenantId(tenantId: string): void {
    write(TENANT_ID_KEY, tenantId);
  },
  clear(): void {
    write(ACCESS_TOKEN_KEY, null);
    write(REFRESH_TOKEN_KEY, null);
    write(TENANT_ID_KEY, null);
  },
};
