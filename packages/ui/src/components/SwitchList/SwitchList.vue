<script setup lang="ts">
/**
 * SwitchList —— 插件开关列表（docs/04 2.3）：加载中 / 失败重试。
 */
import { computed } from 'vue';

export interface SwitchListItem {
  key: string;
  label: string;
  description?: string;
  value: boolean;
  disabled?: boolean;
}

const props = withDefaults(
  defineProps<{
    items: SwitchListItem[];
    loading?: boolean;
    error?: string | null;
    emptyText?: string;
  }>(),
  { emptyText: '暂无插件' },
);

const emit = defineEmits<{
  (e: 'change', key: string, value: boolean): void;
  (e: 'retry'): void;
}>();

const isEmpty = computed(() => !props.loading && !props.error && props.items.length === 0);
</script>

<template>
  <div class="lk-switch-list" v-loading="loading">
    <div v-if="error" class="lk-switch-list__error">
      <span>{{ error }}</span>
      <el-button text type="primary" @click="emit('retry')">重试</el-button>
    </div>

    <p v-else-if="isEmpty" class="lk-switch-list__empty">{{ emptyText }}</p>

    <ul v-else class="lk-switch-list__items">
      <li v-for="item in items" :key="item.key" class="lk-switch-list__item">
        <div class="lk-switch-list__meta">
          <span class="lk-switch-list__label">{{ item.label }}</span>
          <span v-if="item.description" class="lk-switch-list__description">{{ item.description }}</span>
        </div>
        <el-switch
          :model-value="item.value"
          :disabled="item.disabled || loading"
          :active-value="true"
          :inactive-value="false"
          @update:model-value="(value: boolean) => emit('change', item.key, value)"
        />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.lk-switch-list {
  min-height: 48px;
}

.lk-switch-list__error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--lk-space-2) var(--lk-space-3);
  font-size: var(--lk-font-size-xs);
  color: var(--lk-color-danger);
  background: var(--lk-color-danger-bg);
  border-radius: var(--lk-radius-component);
}

.lk-switch-list__empty {
  margin: 0;
  padding: var(--lk-space-4) 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-weak);
  text-align: center;
}

.lk-switch-list__items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.lk-switch-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lk-space-3);
  padding: var(--lk-space-2) 0;
  border-bottom: 0.5px solid var(--lk-border-color);
}

.lk-switch-list__item:last-child {
  border-bottom: none;
}

.lk-switch-list__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lk-switch-list__label {
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-primary);
}

.lk-switch-list__description {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
