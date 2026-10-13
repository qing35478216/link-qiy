<script setup lang="ts">
/**
 * ShareConfigSection —— 应用分享分区（契约 ShareConfig）。
 */
import { computed } from 'vue';
import { useConfigStore } from '@/features/app/stores/config-store';
import { LkConfigSection, LkCopyField } from '@linkai/ui';

const configStore = useConfigStore();
const share = computed(() => configStore.draft.share ?? {});
const dirty = computed(
  () => JSON.stringify(share.value) !== JSON.stringify(configStore.saved.share ?? {}),
);
const shareLink = computed(
  () => `${globalThis.location.origin}/app/${configStore.app?.id ?? ''}`,
);

function update(patch: Partial<typeof share.value>): void {
  configStore.update('share', patch);
}
</script>

<template>
  <LkConfigSection title="应用分享" description="专属链接与公开开关" :dirty="dirty">
    <div class="share-config">
      <div class="share-config__row">
        <span class="share-config__label">专属链接</span>
        <LkCopyField :model-value="shareLink" />
      </div>
      <div class="share-config__row">
        <span class="share-config__label">是否公开</span>
        <el-switch
          :model-value="share.shareEnabled ?? false"
          @update:model-value="(value: boolean) => update({ shareEnabled: value })"
        />
        <span class="share-config__hint">关闭后仅自己可用</span>
      </div>
      <div class="share-config__row">
        <span class="share-config__label">分享路径</span>
        <el-input
          :model-value="share.sharePath ?? ''"
          placeholder="/app/your-path"
          @update:model-value="(value: string) => update({ sharePath: value })"
        />
      </div>
      <div class="share-config__row">
        <span class="share-config__label">显示品牌</span>
        <el-switch
          :model-value="share.showBranding ?? false"
          @update:model-value="(value: boolean) => update({ showBranding: value })"
        />
        <span class="share-config__hint">在嵌入页面展示 Link.AI 品牌标识</span>
      </div>
    </div>
  </LkConfigSection>
</template>

<style scoped>
.share-config {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-3);
  max-width: 640px;
}

.share-config__row {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
}

.share-config__label {
  flex-shrink: 0;
  width: 72px;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-secondary);
}

.share-config__hint {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
