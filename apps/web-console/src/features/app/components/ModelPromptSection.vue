<script setup lang="ts">
/**
 * ModelPromptSection —— 模型设置 + 应用设定分区（契约 ModelPromptConfig）。
 * 模型列表来自 service 面 GET /models（sdk-ts service 客户端 + MSW）。
 */
import { computed } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { ElMessage } from 'element-plus';
import { LkConfigSection, LkModelSelector, LkPromptEditor } from '@linkai/ui';
import type { ModelPromptConfig } from '@/types';
import { serviceAPI } from '@/api';
import { useConfigStore } from '@/features/app/stores/config-store';

const configStore = useConfigStore();
const modelPrompt = computed<ModelPromptConfig>(() => configStore.draft.modelPrompt ?? {});
const dirty = computed(
  () =>
    JSON.stringify(modelPrompt.value) !== JSON.stringify(configStore.saved.modelPrompt ?? {}),
);

const modelsQuery = useQuery({
  queryKey: ['service', 'models'],
  queryFn: async () => (await serviceAPI.listModels()).data,
  staleTime: 5 * 60 * 1000,
});

function update(patch: Partial<NonNullable<typeof modelPrompt.value>>): void {
  configStore.update('modelPrompt', patch);
}

function onOptimize(): void {
  // 一键优化待模型服务联调（model-proxy），Phase 0 占位提示
  ElMessage.info('一键优化待模型服务联调后开放');
}
</script>

<template>
  <LkConfigSection title="模型设置" description="默认模型与采样参数" :dirty="dirty">
    <div class="model-prompt">
      <div class="model-prompt__row">
        <span class="model-prompt__label">默认模型</span>
        <LkModelSelector
          :model-value="modelPrompt.modelCode"
          :models="modelsQuery.data.value?.data ?? []"
          :loading="modelsQuery.isLoading.value"
          placeholder="选择模型"
          @update:model-value="(code: string) => update({ modelCode: code })"
        />
      </div>
      <div class="model-prompt__row">
        <span class="model-prompt__label">温度</span>
        <el-slider
          :model-value="modelPrompt.temperature ?? 0.7"
          :min="0"
          :max="2"
          :step="0.1"
          :format-tooltip="(value: number) => value.toFixed(1)"
          class="model-prompt__slider"
          @update:model-value="(value: number) => update({ temperature: value })"
        />
        <span class="model-prompt__value">{{ (modelPrompt.temperature ?? 0.7).toFixed(1) }}</span>
      </div>
      <div class="model-prompt__row">
        <span class="model-prompt__label">记忆轮次</span>
        <el-input-number
          :model-value="modelPrompt.memoryRounds ?? 10"
          :min="0"
          :max="50"
          @update:model-value="(value: number) => update({ memoryRounds: value })"
        />
        <span class="model-prompt__hint">携带最近 N 轮对话作为上下文</span>
      </div>
      <div class="model-prompt__row">
        <span class="model-prompt__label">上下文长度</span>
        <el-input-number
          :model-value="modelPrompt.contextLength ?? 8000"
          :min="1000"
          :max="200000"
          :step="1000"
          @update:model-value="(value: number) => update({ contextLength: value })"
        />
      </div>
    </div>
  </LkConfigSection>

  <LkConfigSection title="应用设定" description="人设 / 流程 / 约束（系统提示词）" :dirty="dirty">
    <LkPromptEditor
      :model-value="modelPrompt.systemPrompt ?? ''"
      :max-length="8000"
      :variables="(modelPrompt.variables ?? []).map((item) => item.name ?? '').filter(Boolean)"
      placeholder="输入应用设定，如：你是精通太乙神数的专业推演师…"
      @update:model-value="(value: string) => update({ systemPrompt: value })"
      @optimize="onOptimize"
    />
  </LkConfigSection>
</template>

<style scoped>
.model-prompt {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-3);
  max-width: 640px;
}

.model-prompt__row {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
}

.model-prompt__label {
  flex-shrink: 0;
  width: 88px;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-secondary);
}

.model-prompt__slider {
  width: 240px;
}

.model-prompt__value {
  font-size: var(--lk-font-size-xl);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.model-prompt__hint {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
