<script setup lang="ts">
/**
 * VersionGate —— 功能版本门禁（docs/04 2.3）。
 * 当前版本低于要求版本时置灰内容并显示升级引导；达标时透传默认插槽。
 */
import { computed } from 'vue';
import type { QuotaPlan } from '../QuotaBadge/QuotaBadge.vue';

const PLAN_RANK: Record<QuotaPlan, number> = {
  basic: 0,
  standard: 1,
  pro: 2,
  enterprise: 3,
};

const props = withDefaults(
  defineProps<{
    currentPlan?: QuotaPlan;
    requiredPlan: QuotaPlan;
    featureName?: string;
    upgradeUrl?: string;
  }>(),
  { currentPlan: 'basic', featureName: '该功能' },
);

const emit = defineEmits<{
  (e: 'upgrade'): void;
}>();

const allowed = computed(
  () => PLAN_RANK[props.currentPlan] >= PLAN_RANK[props.requiredPlan],
);
</script>

<template>
  <div v-if="allowed" class="lk-version-gate">
    <slot />
  </div>
  <div v-else class="lk-version-gate lk-version-gate--blocked">
    <div class="lk-version-gate__mask" @click.prevent />
    <div class="lk-version-gate__guide">
      <el-icon :size="28" color="var(--lk-color-warning)"><Lock /></el-icon>
      <p class="lk-version-gate__text">{{ featureName }}需要更高版本</p>
      <el-button type="primary" size="small" @click="emit('upgrade')">升级解锁</el-button>
    </div>
  </div>
</template>

<style scoped>
.lk-version-gate {
  position: relative;
  height: 100%;
}

.lk-version-gate--blocked {
  min-height: 120px;
  border-radius: var(--lk-radius-component);
  overflow: hidden;
}

.lk-version-gate__mask {
  position: absolute;
  inset: 0;
  background: var(--lk-bg-page);
  opacity: 0.72;
  pointer-events: all;
  filter: grayscale(1);
}

.lk-version-gate__guide {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--lk-space-2);
}

.lk-version-gate__text {
  margin: 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-secondary);
}
</style>
