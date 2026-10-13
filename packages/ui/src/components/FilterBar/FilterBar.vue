<script setup lang="ts">
/**
 * FilterBar —— 筛选区（docs/04 2.3）。
 * 支持折叠/展开；默认插槽放筛选项，actions 插槽放右侧操作。
 */
import { ref } from 'vue';

withDefaults(
  defineProps<{
    collapsible?: boolean;
    collapsed?: boolean;
  }>(),
  { collapsible: true, collapsed: false },
);

const emit = defineEmits<{
  (e: 'update:collapsed', collapsed: boolean): void;
  (e: 'reset'): void;
}>();

const innerCollapsed = ref(false);

function toggle(): void {
  const collapsed = !innerCollapsed.value;
  innerCollapsed.value = collapsed;
  emit('update:collapsed', collapsed);
}
</script>

<template>
  <div class="lk-filter-bar" :class="{ 'lk-filter-bar--collapsed': collapsed || innerCollapsed }">
    <div class="lk-filter-bar__main">
      <div class="lk-filter-bar__filters">
        <slot />
      </div>
      <div class="lk-filter-bar__actions">
        <slot name="actions" />
        <el-button v-if="$slots.default" text type="primary" @click="emit('reset')">重置</el-button>
        <el-button
          v-if="collapsible"
          text
          :class="{ 'lk-filter-bar__toggle--flipped': collapsed || innerCollapsed }"
          class="lk-filter-bar__toggle"
          @click="toggle"
        >
          {{ collapsed || innerCollapsed ? '展开' : '收起' }}
          <el-icon><ArrowDown /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lk-filter-bar {
  padding: var(--lk-space-3) var(--lk-space-4);
  background: var(--lk-bg-card);
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-card);
}

.lk-filter-bar__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lk-space-3);
}

.lk-filter-bar__filters {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--lk-space-2);
}

.lk-filter-bar--collapsed .lk-filter-bar__filters > :not(:first-child) {
  display: none;
}

.lk-filter-bar__actions {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
}

.lk-filter-bar__toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.lk-filter-bar__toggle--flipped .el-icon {
  transform: rotate(180deg);
}
</style>
