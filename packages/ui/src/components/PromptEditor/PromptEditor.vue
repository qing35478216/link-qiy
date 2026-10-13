<script setup lang="ts">
/**
 * PromptEditor —— 提示词编辑器（docs/04 2.3）。
 * 字符统计 / 变量插入 / 一键优化（optimize 事件由使用方对接模型服务）。
 */
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue: string;
    maxLength?: number;
    placeholder?: string;
    /** 可插入变量名列表，插入格式 {{name}} */
    variables?: string[];
    minRows?: number;
  }>(),
  { maxLength: 8000, minRows: 6 },
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'optimize', value: string): void;
}>();

const length = computed(() => props.modelValue.length);
const overLimit = computed(() => length.value > props.maxLength);

function onInput(event: Event): void {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value);
}

function insertVariable(name: string): void {
  const token = `{{${name}}}`;
  emit('update:modelValue', `${props.modelValue}${token}`);
}
</script>

<template>
  <div class="lk-prompt-editor">
    <div class="lk-prompt-editor__toolbar">
      <div class="lk-prompt-editor__variables">
        <span class="lk-prompt-editor__variables-label">插入变量</span>
        <el-tag
          v-for="name in variables"
          :key="name"
          class="lk-prompt-editor__variable"
          effect="plain"
          round
          @click="insertVariable(name)"
        >
          {{ name }}
        </el-tag>
      </div>
      <el-button text type="primary" :disabled="!modelValue" @click="emit('optimize', modelValue)">
        一键优化
      </el-button>
    </div>

    <el-input
      :model-value="modelValue"
      type="textarea"
      :rows="minRows"
      :placeholder="placeholder ?? '输入应用设定（人设/流程/约束）…'"
      :maxlength="maxLength"
      show-word-limit
      resize="none"
      @input="onInput"
    />

    <div class="lk-prompt-editor__footer">
      <span class="lk-prompt-editor__count" :class="{ 'lk-prompt-editor__count--over': overLimit }">
        {{ length }}/{{ maxLength }}
      </span>
      <span class="lk-prompt-editor__hint">支持 {'{{变量}}'} 占位符</span>
    </div>
  </div>
</template>

<style scoped>
.lk-prompt-editor {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-2);
}

.lk-prompt-editor__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lk-space-2);
}

.lk-prompt-editor__variables {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--lk-space-1);
}

.lk-prompt-editor__variables-label {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-prompt-editor__variable {
  cursor: pointer;
}

.lk-prompt-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-prompt-editor__count--over {
  color: var(--lk-color-danger);
}
</style>
