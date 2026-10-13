<script setup lang="ts">
/**
 * DebugDrawer —— 右侧调试抽屉（docs/04 2.3）：默认 400px，不打断配置流。
 */
withDefaults(
  defineProps<{
    modelValue: boolean;
    title?: string;
    width?: number;
  }>(),
  { title: '调试', width: 400 },
);

const emit = defineEmits<{
  (e: 'update:modelValue', visible: boolean): void;
}>();
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    :size="width"
    direction="rtl"
    :with-header="true"
    class="lk-debug-drawer"
    @update:model-value="(visible: boolean) => emit('update:modelValue', visible)"
    @close="emit('update:modelValue', false)"
  >
    <div class="lk-debug-drawer__body">
      <slot />
    </div>
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-drawer>
</template>

<style scoped>
.lk-debug-drawer__body {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>
