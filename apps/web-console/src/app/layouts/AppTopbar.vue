<script setup lang="ts">
/**
 * AppTopbar —— 顶栏：通知铃 / 文档 / 版本徽标+配额面板（QuotaBadge）/ 头像。
 * 配额数据来自 GET /quota/summary（TanStack Query，5 分钟 stale）。
 */
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useQuery } from '@tanstack/vue-query';
import { ElMessageBox } from 'element-plus';
import { consoleAPI } from '@/api';
import { useAuthStore } from '@/app/stores/auth-store';

const authStore = useAuthStore();
const router = useRouter();

const { data: quota, isLoading } = useQuery({
  queryKey: ['quota', 'summary'],
  queryFn: async () => (await consoleAPI.getQuotaSummary()).data,
  staleTime: 5 * 60 * 1000,
});

const nickname = computed(() => authStore.profile?.nickname ?? authStore.profile?.phone ?? '未登录');
const avatarText = computed(() => nickname.value.slice(0, 1).toUpperCase());

async function onLogout(): Promise<void> {
  await ElMessageBox.confirm('确认退出登录？', '退出', { type: 'warning' });
  await authStore.logout();
  await router.push({ name: 'login' });
}
</script>

<template>
  <header class="app-topbar">
    <div class="app-topbar__left" />

    <div class="app-topbar__right">
      <el-tooltip content="通知" placement="bottom">
        <el-badge :value="0" class="app-topbar__icon">
          <el-icon :size="18"><Bell /></el-icon>
        </el-badge>
      </el-tooltip>
      <el-tooltip content="帮助文档" placement="bottom">
        <el-icon :size="18" class="app-topbar__icon" @click="router.push('/console/docs')">
          <QuestionFilled />
        </el-icon>
      </el-tooltip>

      <LkQuotaBadge
        :plan-badge="quota?.planBadge"
        :plan="quota?.plan"
        :wallet-balance="quota?.walletBalance"
        :upgrade-url="quota?.upgradeUrl"
        :usage="quota?.usage"
        :loading="isLoading"
      />

      <el-dropdown trigger="click">
        <div class="app-topbar__avatar">
          <img v-if="authStore.profile?.avatarUrl" :src="authStore.profile.avatarUrl" alt="" />
          <span v-else>{{ avatarText }}</span>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>{{ nickname }}</el-dropdown-item>
            <el-dropdown-item divided @click="onLogout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<style scoped>
.app-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--lk-topbar-height);
  padding: 0 var(--lk-space-6);
  background: var(--lk-bg-card);
  border-bottom: 0.5px solid var(--lk-border-color);
}

.app-topbar__right {
  display: flex;
  align-items: center;
  gap: var(--lk-space-4);
}

.app-topbar__icon {
  display: inline-flex;
  color: var(--lk-text-secondary);
  cursor: pointer;
}

.app-topbar__icon:hover {
  color: var(--lk-color-primary);
}

.app-topbar__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  overflow: hidden;
  font-size: var(--lk-font-size-sm);
  font-weight: 600;
  color: var(--lk-text-inverse);
  background: var(--lk-color-primary);
  border-radius: var(--lk-radius-round);
  cursor: pointer;
}

.app-topbar__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
