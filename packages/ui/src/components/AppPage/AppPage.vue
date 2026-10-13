<script setup lang="ts">
/**
 * AppPage —— 页头 + 内容区骨架（docs/04 2.3）。
 * 所有控制台列表/配置页统一结构：页头（标题+描述+主操作右对齐）+ 内容区。
 */
defineProps<{
  title: string;
  description?: string;
  loading?: boolean;
  error?: string | null;
}>();

const emit = defineEmits<{
  (e: 'retry'): void;
}>();
</script>

<template>
  <section class="lk-app-page" v-loading="loading">
    <header class="lk-app-page__header">
      <div class="lk-app-page__heading">
        <h2 class="lk-app-page__title">{{ title }}</h2>
        <p v-if="description" class="lk-app-page__description">{{ description }}</p>
      </div>
      <div class="lk-app-page__actions">
        <slot name="actions" />
      </div>
    </header>

    <el-alert
      v-if="error"
      class="lk-app-page__error"
      type="error"
      :closable="false"
      show-icon
      :title="error"
    >
      <template #default>
        <el-button type="primary" text class="lk-app-page__retry" @click="emit('retry')">
          重试
        </el-button>
      </template>
    </el-alert>

    <div class="lk-app-page__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.lk-app-page {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-4);
  min-height: 100%;
}

.lk-app-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--lk-space-4);
}

.lk-app-page__title {
  margin: 0;
  font-size: var(--lk-font-size-lg);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.lk-app-page__description {
  margin: var(--lk-space-1) 0 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-app-page__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--lk-space-2);
}

.lk-app-page__error {
  border-radius: var(--lk-radius-component);
}

.lk-app-page__retry {
  margin-left: var(--lk-space-2);
}

.lk-app-page__body {
  flex: 1;
}
</style>
