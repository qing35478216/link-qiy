<script setup lang="ts">
/**
 * CreateAppModal —— 创建应用弹窗（视觉基准：linkai-screenshots/01-factory）。
 * 两个大卡片：轻量应用（一段提示词快速创建）/ 知识库应用（私有数据定制问答）。
 */
import { reactive, ref } from 'vue';
import type { AppType } from '@/types';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', visible: boolean): void;
  (e: 'create', payload: { name: string; description?: string; type: AppType }): void;
}>();

const form = reactive({
  type: 'lightweight' as AppType,
  name: '',
  description: '',
});
const submitting = ref(false);

function close(): void {
  emit('update:modelValue', false);
}

function submit(): void {
  if (!form.name.trim()) return;
  submitting.value = true;
  emit('create', {
    name: form.name.trim(),
    description: form.description.trim() || undefined,
    type: form.type,
  });
  submitting.value = false;
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="创建应用"
    width="560px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="form.name = ''; form.description = ''"
  >
    <div class="create-app__types">
      <div
        class="create-app__type"
        :class="{ 'create-app__type--active': form.type === 'lightweight' }"
        @click="form.type = 'lightweight'"
      >
        <h4 class="create-app__type-title">轻量应用</h4>
        <p class="create-app__type-desc">一段提示词快速创建，适合人设/文案/推理类助手</p>
      </div>
      <div
        class="create-app__type"
        :class="{ 'create-app__type--active': form.type === 'knowledge' }"
        @click="form.type = 'knowledge'"
      >
        <h4 class="create-app__type-title">知识库应用</h4>
        <p class="create-app__type-desc">基于私有数据定制问答，适合企业知识/文档助手</p>
      </div>
    </div>

    <el-form label-position="top" class="create-app__form">
      <el-form-item label="应用名称" required>
        <el-input v-model="form.name" placeholder="请输入应用名称" maxlength="64" />
      </el-form-item>
      <el-form-item label="应用描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          placeholder="一句话描述这个应用（可选）"
          maxlength="512"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!form.name.trim()" @click="submit">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.create-app__types {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--lk-space-3);
  margin-bottom: var(--lk-space-4);
}

.create-app__type {
  padding: var(--lk-space-4);
  border: 1px solid var(--lk-border-color);
  border-radius: var(--lk-radius-component);
  cursor: pointer;
}

.create-app__type--active {
  border: 2px solid var(--lk-color-primary);
}

.create-app__type-title {
  margin: 0 0 var(--lk-space-1);
  font-size: var(--lk-font-size-md);
  color: var(--lk-text-primary);
}

.create-app__type-desc {
  margin: 0;
  font-size: var(--lk-font-size-xs);
  line-height: 1.6;
  color: var(--lk-text-weak);
}
</style>
