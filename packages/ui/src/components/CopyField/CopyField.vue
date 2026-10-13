<script setup lang="ts">
/**
 * CopyField —— 复制字段（docs/04 2.3）：链接 / Key / Code 一键复制，带成功反馈。
 */
import { ref } from 'vue';
import { ElMessage } from 'element-plus';

withDefaults(
  defineProps<{
    modelValue: string;
    label?: string;
    monospace?: boolean;
    multiline?: boolean;
  }>(),
  { monospace: true, multiline: false },
);

const copied = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

async function copy(value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    // 降级：选中文本让用户手动复制
    const input = document.activeElement as HTMLInputElement | null;
    input?.select?.();
  }
  copied.value = true;
  ElMessage.success('已复制');
  clearTimeout(timer);
  timer = setTimeout(() => {
    copied.value = false;
  }, 2000);
}
</script>

<template>
  <div class="lk-copy-field">
    <span v-if="label" class="lk-copy-field__label">{{ label }}</span>
    <div class="lk-copy-field__row">
      <el-input
        :model-value="modelValue"
        :type="multiline ? 'textarea' : 'text'"
        :rows="multiline ? 3 : undefined"
        readonly
        :class="{ 'lk-copy-field__mono': monospace }"
        class="lk-copy-field__input"
      />
      <el-button
        :type="copied ? 'success' : 'default'"
        round
        class="lk-copy-field__button"
        @click="copy(modelValue)"
      >
        {{ copied ? '已复制' : '复制' }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.lk-copy-field {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
}

.lk-copy-field__label {
  flex-shrink: 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-secondary);
}

.lk-copy-field__row {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--lk-space-2);
}

.lk-copy-field__mono :deep(.el-input__inner) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: var(--lk-font-size-xs);
}
</style>
