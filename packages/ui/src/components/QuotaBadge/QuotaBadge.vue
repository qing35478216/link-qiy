<script setup lang="ts">
/**
 * QuotaBadge —— 版本徽标 + 配额面板（docs/04 2.3）。
 * 徽标点击展开悬浮面板：积分余额 / 消息与 Token 用量 / 升级入口；超限红色提示。
 */
import { computed } from 'vue';

export type QuotaPlan = 'basic' | 'standard' | 'pro' | 'enterprise';

const props = withDefaults(
  defineProps<{
    planBadge?: string;
    plan?: QuotaPlan;
    walletBalance?: number;
    upgradeUrl?: string;
    usage?: {
      messagesUsed?: number;
      messagesLimit?: number;
      tokensUsed?: number;
      tokensLimit?: number;
    };
    loading?: boolean;
  }>(),
  { planBadge: '基础版', plan: 'basic' },
);

const emit = defineEmits<{
  (e: 'upgrade'): void;
}>();

interface UsageRow {
  key: string;
  label: string;
  used: number;
  limit?: number;
  unit: string;
}

const rows = computed<UsageRow[]>(() => {
  const usage = props.usage ?? {};
  const list: UsageRow[] = [
    { key: 'messages', label: '消息数', used: usage.messagesUsed ?? 0, limit: usage.messagesLimit, unit: '条' },
    { key: 'tokens', label: 'Token', used: usage.tokensUsed ?? 0, limit: usage.tokensLimit, unit: '' },
  ];
  return list;
});

const anyExceeded = computed(() =>
  rows.value.some((row) => row.limit !== undefined && row.used >= row.limit),
);

function percent(row: UsageRow): number {
  if (!row.limit || row.limit <= 0) return 0;
  return Math.min(100, Math.round((row.used / row.limit) * 100));
}

function isExceeded(row: UsageRow): boolean {
  return row.limit !== undefined && row.used >= row.limit;
}
</script>

<template>
  <el-popover placement="bottom-end" :width="280" trigger="click" :show-after="0">
    <template #reference>
      <span class="lk-quota-badge" :class="`lk-quota-badge--${plan}`" v-loading="loading">
        {{ planBadge }}
      </span>
    </template>

    <div class="lk-quota-panel">
      <div class="lk-quota-panel__header">
        <span class="lk-quota-panel__title">配额面板</span>
        <span class="lk-quota-panel__plan">{{ planBadge }}</span>
      </div>

      <el-alert
        v-if="anyExceeded"
        type="error"
        :closable="false"
        show-icon
        title="已超限，升级后可继续使用"
        class="lk-quota-panel__alert"
      />

      <div class="lk-quota-panel__row">
        <span class="lk-quota-panel__label">积分余额</span>
        <span class="lk-quota-panel__value">{{ walletBalance ?? 0 }}</span>
      </div>

      <div v-for="row in rows" :key="row.key" class="lk-quota-panel__row">
        <span class="lk-quota-panel__label">{{ row.label }}</span>
        <span class="lk-quota-panel__value" :class="{ 'lk-quota-panel__value--over': isExceeded(row) }">
          {{ row.used }}{{ row.unit }}<template v-if="row.limit !== undefined"> / {{ row.limit }}{{ row.unit }}</template>
        </span>
      </div>
      <el-progress
        v-for="row in rows"
        :key="`${row.key}-bar`"
        :percentage="percent(row)"
        :color="isExceeded(row) ? 'var(--lk-color-danger)' : undefined"
        :show-text="false"
        :stroke-width="6"
        class="lk-quota-panel__bar"
      />

      <el-button
        v-if="upgradeUrl"
        type="primary"
        size="small"
        class="lk-quota-panel__upgrade"
        @click="emit('upgrade')"
      >
        升级版本
      </el-button>
    </div>
  </el-popover>
</template>

<style scoped>
.lk-quota-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--lk-space-2);
  font-size: var(--lk-font-size-xs);
  border-radius: var(--lk-radius-round);
  cursor: pointer;
  user-select: none;
}

.lk-quota-badge--basic {
  color: var(--lk-plan-basic-text);
  background: var(--lk-plan-basic-bg);
}

.lk-quota-badge--pro {
  color: var(--lk-plan-pro-text);
  background: var(--lk-plan-pro-bg);
}

.lk-quota-badge--standard {
  color: var(--lk-plan-enterprise-text);
  background: var(--lk-plan-enterprise-bg);
}

.lk-quota-badge--enterprise {
  color: var(--lk-plan-enterprise-text);
  background: var(--lk-plan-enterprise-bg);
}

.lk-quota-panel {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-2);
}

.lk-quota-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.lk-quota-panel__title {
  font-size: var(--lk-font-size-sm);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.lk-quota-panel__plan {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-quota-panel__alert {
  border-radius: var(--lk-radius-component);
}

.lk-quota-panel__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--lk-font-size-xs);
}

.lk-quota-panel__label {
  color: var(--lk-text-secondary);
}

.lk-quota-panel__value {
  font-size: var(--lk-font-size-xl);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.lk-quota-panel__value--over {
  color: var(--lk-color-danger);
}

.lk-quota-panel__bar {
  margin-bottom: var(--lk-space-1);
}

.lk-quota-panel__upgrade {
  margin-top: var(--lk-space-2);
}
</style>
