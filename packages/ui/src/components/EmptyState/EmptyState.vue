<script setup lang="ts">
/**
 * EmptyState —— 空状态（docs/04 2.3）：插图 + 文案 + CTA。
 * 铁律：不允许空白页；默认插槽放主操作按钮。
 */
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    title: string;
    description?: string;
    /** 自定义插图 URL；缺省用内置 SVG */
    image?: string;
    size?: 'small' | 'medium';
  }>(),
  { size: 'medium' },
);

const useBuiltin = computed(() => !props.image);
</script>

<template>
  <div class="lk-empty-state" :class="`lk-empty-state--${size}`">
    <slot name="image">
      <img v-if="image" :src="image" class="lk-empty-state__image" alt="" />
      <svg
        v-else-if="useBuiltin"
        class="lk-empty-state__image"
        viewBox="0 0 160 120"
        fill="none"
        aria-hidden="true"
      >
        <rect x="30" y="24" width="100" height="72" rx="8" fill="var(--lk-bg-hover)" />
        <rect x="42" y="40" width="76" height="8" rx="4" fill="var(--lk-border-color-strong)" />
        <rect x="42" y="56" width="56" height="8" rx="4" fill="var(--lk-border-color-strong)" />
        <rect x="42" y="72" width="40" height="8" rx="4" fill="var(--lk-border-color-strong)" />
        <circle cx="118" cy="86" r="16" fill="var(--lk-color-primary-bg)" />
        <path d="M112 86h12M118 80v12" stroke="var(--lk-color-primary)" stroke-width="2.5" stroke-linecap="round" />
      </svg>
    </slot>
    <p class="lk-empty-state__title">{{ title }}</p>
    <p v-if="description" class="lk-empty-state__description">{{ description }}</p>
    <div v-if="$slots.default" class="lk-empty-state__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.lk-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--lk-space-8) var(--lk-space-4);
  text-align: center;
}

.lk-empty-state--small {
  padding: var(--lk-space-6) var(--lk-space-4);
}

.lk-empty-state__image {
  width: 160px;
  height: 120px;
}

.lk-empty-state--small .lk-empty-state__image {
  width: 96px;
  height: 72px;
}

.lk-empty-state__title {
  margin: var(--lk-space-3) 0 0;
  font-size: var(--lk-font-size-md);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.lk-empty-state__description {
  margin: var(--lk-space-1) 0 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-empty-state__actions {
  margin-top: var(--lk-space-4);
}
</style>
