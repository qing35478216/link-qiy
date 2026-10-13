<script setup lang="ts">
/**
 * BasicInfoSection —— 基础信息分区（App 字段：name/description/type/iconUrl）。
 * 契约：应用基础信息属 App（PATCH /apps/:id），与七件套（PUT config）分两个端点；
 * 由配置页整页保存时统一提交（见 config-store.save）。
 */
import { computed } from 'vue';
import { useConfigStore } from '@/features/app/stores/config-store';
import { LkConfigSection } from '@linkai/ui';
import { deleteApp } from '@/features/app/api/app-api';
import { ElMessage, ElMessageBox } from 'element-plus';

const configStore = useConfigStore();
const app = computed(() => configStore.app);
const dirty = computed(() => configStore.isDirty);

async function onDelete(): Promise<void> {
  if (!app.value?.id) return;
  await ElMessageBox.confirm(
    `删除应用「${app.value.name}」？该操作不可恢复`,
    '删除应用',
    { type: 'warning' },
  );
  try {
    await deleteApp(app.value.id);
    ElMessage.success('已删除');
    window.location.href = '/console/factory';
  } catch {
    ElMessage.error('删除失败，请重试');
  }
}
</script>

<template>
  <LkConfigSection title="基础信息" description="应用名称、类型与头像" :dirty="dirty">
    <el-form label-width="88px" class="basic-info">
      <el-form-item label="应用名称">
        <el-input
          :model-value="app?.name"
          placeholder="请输入应用名称"
          maxlength="64"
          @update:model-value="(value: string) => configStore.updateAppInfo({ name: value })"
        />
      </el-form-item>
      <el-form-item label="应用类型">
        <el-tag :type="app?.type === 'knowledge' ? 'warning' : 'primary'" effect="light">
          {{ app?.type === 'knowledge' ? '知识应用' : '轻量应用' }}
        </el-tag>
        <span class="basic-info__hint">类型创建后不可变更</span>
      </el-form-item>
      <el-form-item label="应用描述">
        <el-input
          :model-value="app?.description"
          type="textarea"
          :rows="2"
          maxlength="512"
          @update:model-value="(value: string) => configStore.updateAppInfo({ description: value })"
        />
      </el-form-item>
      <el-form-item label="应用头像">
        <el-button disabled title="AI 生成头像待模型服务联调">AI 生成</el-button>
        <el-input
          :model-value="app?.iconUrl"
          placeholder="头像 URL（可选）"
          class="basic-info__icon-url"
          @update:model-value="(value: string) => configStore.updateAppInfo({ iconUrl: value })"
        />
      </el-form-item>
      <el-form-item label="删除应用">
        <el-button type="danger" plain @click="onDelete">删除应用</el-button>
      </el-form-item>
    </el-form>
  </LkConfigSection>
</template>

<style scoped>
.basic-info {
  max-width: 560px;
}

.basic-info__hint {
  margin-left: var(--lk-space-2);
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.basic-info__icon-url {
  margin-left: var(--lk-space-2);
  width: 280px;
}
</style>
