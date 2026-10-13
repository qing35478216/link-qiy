/**
 * auth-store —— 登录态（Pinia）。
 * 契约：手机号 + 短信验证码登录；令牌与租户 ID 落 token-store（见 api/token-store.ts）。
 */
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { Ref } from 'vue';
import { consoleAPI, tokenStore } from '@/api';
import type { UserProfile } from '@/types';

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(tokenStore.getAccessToken());
  const refreshToken = ref<string | null>(tokenStore.getRefreshToken());
  const tenantId = ref<string | null>(tokenStore.getTenantId());
  const profile = ref<UserProfile | null>(null);

  const isAuthenticated = computed(() => Boolean(accessToken.value));

  function restore(): void {
    accessToken.value = tokenStore.getAccessToken();
    refreshToken.value = tokenStore.getRefreshToken();
    tenantId.value = tokenStore.getTenantId();
  }

  async function sendSmsCode(phone: string): Promise<void> {
    await consoleAPI.sendSmsCode({ phone, scene: 'login' });
  }

  async function loginWithPhone(phone: string, smsCode: string, agreementAccepted: boolean): Promise<void> {
    const response = await consoleAPI.loginByPhone({ phone, smsCode, agreementAccepted });
    const { accessToken: token, refreshToken: nextRefresh } = response.data;
    tokenStore.setTokens(token, nextRefresh);
    // 响应拦截器已捕获 x-tenant-id，这里同步回 store
    restore();
  }

  async function loadProfile(): Promise<UserProfile | null> {
    if (!accessToken.value) return null;
    const response = await consoleAPI.getMyProfile();
    profile.value = response.data;
    return profile.value;
  }

  async function logout(): Promise<void> {
    try {
      await consoleAPI.logout();
    } catch {
      // 登出失败不阻塞本地清理
    }
    clear();
  }

  function clear(): void {
    tokenStore.clear();
    accessToken.value = null;
    refreshToken.value = null;
    tenantId.value = null;
    profile.value = null;
  }

  return {
    accessToken: accessToken as Ref<string | null>,
    refreshToken: refreshToken as Ref<string | null>,
    tenantId: tenantId as Ref<string | null>,
    profile,
    isAuthenticated,
    restore,
    sendSmsCode,
    loginWithPhone,
    loadProfile,
    logout,
    clear,
  };
});
