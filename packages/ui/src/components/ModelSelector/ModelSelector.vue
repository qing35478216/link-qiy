<script setup lang="ts">
/**
 * ModelSelector —— 模型下拉（docs/04 2.3）：搜索 / 能力标签 / 价格。
 * 选项结构由使用方从 sdk-ts 的 service Model 列表映射传入（组件不依赖契约）。
 */
import { computed } from 'vue';

export interface ModelSelectorOption {
  code: string;
  name: string;
  provider?: string;
  capabilities?: string[];
  contextLength?: number;
  price?: { inputPer1k?: number; outputPer1k?: number; creditPerCall?: number };
}

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    models: ModelSelectorOption[];
    loading?: boolean;
    disabled?: boolean;
    placeholder?: string;
  }>(),
  { placeholder: '选择模型' },
);

const emit = defineEmits<{
  (e: 'update:modelValue', code: string): void;
  (e: 'change', option: ModelSelectorOption | undefined): void;
}>();

const selected = computed(() => props.models.find((model) => model.code === props.modelValue));

function priceText(option: ModelSelectorOption): string {
  const { price } = option;
  if (!price) return '';
  if (price.creditPerCall !== undefined) return `${price.creditPerCall} 积分/次`;
  const parts: string[] = [];
  if (price.inputPer1k !== undefined) parts.push(`入 $${price.inputPer1k}/1k`);
  if (price.outputPer1k !== undefined) parts.push(`出 $${price.outputPer1k}/1k`);
  return parts.join(' · ');
}

function onChange(code: string): void {
  emit('update:modelValue', code);
  emit('change', props.models.find((model) => model.code === code));
}
</script>

<template>
  <div class="lk-model-selector">
    <el-select
      :model-value="modelValue"
      :loading="loading"
      :disabled="disabled"
      :placeholder="placeholder"
      filterable
      clearable
      class="lk-model-selector__select"
      @change="onChange"
    >
      <el-option
        v-for="model in models"
        :key="model.code"
        :value="model.code"
        :label="model.name"
        :disabled="model.enabled === false"
      >
        <div class="lk-model-selector__option">
          <span class="lk-model-selector__name">{{ model.name }}</span>
          <span v-if="model.provider" class="lk-model-selector__provider">{{ model.provider }}</span>
          <span v-for="capability in model.capabilities ?? []" :key="capability" class="lk-model-selector__capability">
            {{ capability }}
          </span>
          <span v-if="model.price" class="lk-model-selector__price">{{ priceText(model) }}</span>
        </div>
      </el-option>
    </el-select>
    <span v-if="selected" class="lk-model-selector__selected-hint">
      {{ selected.name }}<template v-if="selected.contextLength"> · 上下文 {{ selected.contextLength }}</template>
    </span>
  </div>
</template>

<style scoped>
.lk-model-selector {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
}

.lk-model-selector__select {
  width: 260px;
}

.lk-model-selector__option {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
  font-size: var(--lk-font-size-sm);
}

.lk-model-selector__name {
  font-weight: 500;
  color: var(--lk-text-primary);
}

.lk-model-selector__provider,
.lk-model-selector__capability {
  padding: 0 6px;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
  background: var(--lk-bg-hover);
  border-radius: var(--lk-radius-round);
}

.lk-model-selector__price {
  margin-left: auto;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-secondary);
}

.lk-model-selector__selected-hint {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
