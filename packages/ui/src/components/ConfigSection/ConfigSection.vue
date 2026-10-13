<script setup lang="ts">
/**
 * ConfigSection —— 配置分区（docs/04 2.3）：标题 + 描述 + 内容 + 保存提示。
 * dirty 为 true 时显示脏标记圆点；任一分区改动即整页脏（由使用方统一计算）。
 */
import { computed, ref } from 'vue';

const props = withDefaults(
  defineProps<{
    title: string;
    description?: string;
    dirty?: boolean;
    collapsible?: boolean;
    defaultCollapsed?: boolean;
    disabled?: boolean;
  }>(),
  { collapsible: false, defaultCollapsed: false, disabled: false },
);

const collapsed = ref(props.defaultCollapsed);
const isCollapsed = computed(() => props.collapsible && collapsed.value);
</script>

<template>
  <section class="lk-config-section" :class="{ 'lk-config-section--disabled': disabled }">
    <header class="lk-config-section__header">
      <div class="lk-config-section__heading">
        <h3 class="lk-config-section__title">
          {{ title }}
          <span v-if="dirty" class="lk-config-section__dirty" title="有未保存的修改" />
        </h3>
        <p v-if="description" class="lk-config-section__description">{{ description }}</p>
      </div>
      <div class="lk-config-section__extra">
        <slot name="extra" />
        <el-button
          v-if="collapsible"
          text
          class="lk-config-section__collapse"
          @click="collapsed = !collapsed"
        >
          {{ isCollapsed ? '展开' : '收起' }}
          <el-icon :class="{ 'lk-config-section__icon--flipped': isCollapsed }"><ArrowDown /></el-icon>
        </el-button>
      </div>
    </header>

    <div v-show="!isCollapsed" class="lk-config-section__body">
      <slot />
    </div>

    <footer v-if="$slots.footer" class="lk-config-section__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.lk-config-section {
  padding: var(--lk-space-4);
  background: var(--lk-bg-card);
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-card);
}

.lk-config-section--disabled {
  opacity: 0.6;
}

.lk-config-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--lk-space-3);
}

.lk-config-section__title {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
  margin: 0;
  font-size: var(--lk-font-size-md);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.lk-config-section__dirty {
  width: 6px;
  height: 6px;
  border-radius: var(--lk-radius-round);
  background: var(--lk-color-warning);
}

.lk-config-section__description {
  margin: var(--lk-space-1) 0 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-config-section__extra {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
}

.lk-config-section__body {
  margin-top: var(--lk-space-4);
}

.lk-config-section__footer {
  margin-top: var(--lk-space-3);
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-config-section__icon--flipped {
  transform: rotate(180deg);
}
</style>
