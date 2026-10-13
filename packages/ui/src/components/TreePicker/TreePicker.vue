<script setup lang="ts">
/**
 * TreePicker —— 目录/知识库选择（docs/04 2.3）。
 * 多选；folderSelectAll（默认开）= 勾选目录全选子节点（严格模式关闭级联）。
 */
import { computed } from 'vue';

export interface TreePickerNode {
  key: string;
  label: string;
  children?: TreePickerNode[];
  disabled?: boolean;
}

const props = withDefaults(
  defineProps<{
    modelValue: string[];
    data: TreePickerNode[];
    folderSelectAll?: boolean;
    placeholder?: string;
  }>(),
  { folderSelectAll: true, placeholder: '请选择' },
);

const emit = defineEmits<{
  (e: 'update:modelValue', keys: string[]): void;
  (e: 'change', keys: string[]): void;
}>();

const treeProps = computed(() => ({ label: 'label', children: 'children' }));

function onCheck(_node: unknown, { checkedKeys }: { checkedKeys: (string | number)[] }): void {
  const keys = checkedKeys.map((key) => String(key));
  emit('update:modelValue', keys);
  emit('change', keys);
}
</script>

<template>
  <div class="lk-tree-picker">
    <el-input v-if="modelValue.length === 0" :model-value="placeholder" readonly class="lk-tree-picker__placeholder" />
    <el-input v-else :model-value="`已选 ${modelValue.length} 项`" readonly class="lk-tree-picker__placeholder" />
    <el-tree
      ref="treeRef"
      :data="data"
      :props="treeProps"
      show-checkbox
      :check-strictly="!folderSelectAll"
      :default-checked-keys="modelValue"
      node-key="key"
      class="lk-tree-picker__tree"
      @check="onCheck"
    />
  </div>
</template>

<style scoped>
.lk-tree-picker {
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-component);
  overflow: hidden;
}

.lk-tree-picker__placeholder {
  pointer-events: none;
}

.lk-tree-picker__placeholder :deep(.el-input__wrapper) {
  box-shadow: none;
  border-radius: 0;
  background: var(--lk-bg-hover);
}

.lk-tree-picker__tree {
  padding: var(--lk-space-2);
  background: var(--lk-bg-card);
}
</style>
