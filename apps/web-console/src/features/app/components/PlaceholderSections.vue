<script setup lang="ts">
/**
 * PlaceholderSections —— 配置七件套剩余分区（知识库 / 数据 / 插件 / 高级）。
 * 契约字段已就位（KnowledgeConfig / DataConfig / PluginsConfig / AdvancedConfig），
 * Phase 0 展示表单框架与字段只读预览，交互由后续 feature 工单落地。
 */
import { computed } from 'vue';
import { LkConfigSection, LkSwitchList } from '@linkai/ui';
import type { SwitchListItem } from '@linkai/ui';
import { useConfigStore } from '@/features/app/stores/config-store';

const configStore = useConfigStore();
const knowledge = computed(() => configStore.draft.knowledge ?? {});
const data = computed(() => configStore.draft.data ?? {});
const plugins = computed(() => configStore.draft.plugins ?? {});
const advanced = computed(() => configStore.draft.advanced ?? {});

const pluginSwitches = computed<SwitchListItem[]>(() => [
  { key: 'vision', label: '图像识别', value: (plugins.value.pluginIds ?? []).includes('vision'), disabled: true },
  { key: 'search', label: '谷歌搜索', value: (plugins.value.pluginIds ?? []).includes('search'), disabled: true },
  { key: 'web-read', label: '网页速读', value: (plugins.value.pluginIds ?? []).includes('web-read'), disabled: true },
]);
</script>

<template>
  <LkConfigSection
    title="知识库配置"
    description="关联知识库与检索策略（知识应用可用）"
    :dirty="JSON.stringify(knowledge) !== JSON.stringify(configStore.saved.knowledge ?? {})"
    disabled
  >
    <div class="placeholder-section">
      <p class="placeholder-section__hint">
        关联知识库：{{ knowledge.datasetIds?.length ?? 0 }} 个 ·
        检索阈值 {{ knowledge.similarityThreshold ?? 0.8 }} ·
        TopK {{ knowledge.semanticTopK ?? 5 }}
      </p>
      <p class="placeholder-section__todo">目录树选择器与检索测试由「知识框架」工单交付</p>
    </div>
  </LkConfigSection>

  <LkConfigSection
    title="数据配置"
    description="绑定数据库模块数据集与同步周期"
    :dirty="JSON.stringify(data) !== JSON.stringify(configStore.saved.data ?? {})"
    disabled
  >
    <div class="placeholder-section">
      <p class="placeholder-section__hint">
        数据集：{{ data.dbDatasetId || '未绑定' }} · 同步周期：{{ data.tableSyncCron || '未设置' }}
      </p>
      <p class="placeholder-section__todo">数据库模块由后续工单交付</p>
    </div>
  </LkConfigSection>

  <LkConfigSection
    title="插件配置"
    description="为应用挂载工具插件"
    :dirty="JSON.stringify(plugins) !== JSON.stringify(configStore.saved.plugins ?? {})"
    disabled
  >
    <LkSwitchList :items="pluginSwitches" empty-text="暂无插件" />
    <p class="placeholder-section__todo">插件中心由「工具框架」工单交付</p>
  </LkConfigSection>

  <LkConfigSection
    title="高级配置"
    description="人工转接与限流"
    :dirty="JSON.stringify(advanced) !== JSON.stringify(configStore.saved.advanced ?? {})"
    disabled
  >
    <div class="placeholder-section">
      <p class="placeholder-section__hint">
        人工转接：{{ advanced.humanTransferEnabled ? '开' : '关' }} ·
        限流 {{ advanced.rateLimitQpm ?? 60 }} 次/分钟
      </p>
      <p class="placeholder-section__todo">高级配置交互由后续工单交付</p>
    </div>
  </LkConfigSection>
</template>

<style scoped>
.placeholder-section {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-1);
}

.placeholder-section__hint {
  margin: 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-secondary);
}

.placeholder-section__todo {
  margin: 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
