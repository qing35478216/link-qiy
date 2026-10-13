<script setup lang="ts">
/**
 * FileUploader —— 文件上传（docs/04 2.3）：进度 / 类型校验 / 大小超限。
 * 仅做前端校验与列表管理，实际上传由使用方接管 change 事件。
 */
import { ref } from 'vue';
import { ElMessage, ElUpload } from 'element-plus';
import type { UploadFile, UploadFiles, UploadInstance } from 'element-plus';

export interface UploadFileItem {
  name: string;
  size: number;
  status: 'ready' | 'uploading' | 'done' | 'error';
  percent: number;
}

const props = withDefaults(
  defineProps<{
    accept?: string;
    maxSizeMb?: number;
    multiple?: boolean;
    disabled?: boolean;
    tip?: string;
  }>(),
  { accept: '.pdf,.docx,.txt,.md', maxSizeMb: 20, multiple: true, tip: '支持 PDF/Word/TXT/Markdown' },
);

const emit = defineEmits<{
  (e: 'change', files: UploadFileItem[]): void;
  (e: 'error', message: string): void;
}>();

const fileList = ref<UploadFileItem[]>([]);
const uploadRef = ref<UploadInstance>();

function validate(file: { name: string; size?: number }): string | null {
  const maxBytes = props.maxSizeMb * 1024 * 1024;
  if ((file.size ?? 0) > maxBytes) return `「${file.name}」超过 ${props.maxSizeMb}MB 限制`;
  if (props.accept) {
    const exts = props.accept.split(',').map((ext) => ext.trim().toLowerCase());
    const lower = file.name.toLowerCase();
    if (!exts.some((ext) => lower.endsWith(ext))) {
      return `「${file.name}」类型不支持，仅接受 ${props.accept}`;
    }
  }
  return null;
}

function onExceed(): void {
  const message = `一次最多上传 10 个文件`;
  ElMessage.warning(message);
  emit('error', message);
}

/** el-upload 的 change 回调：第一个参数是原始 File（EP 内部已挂 uid） */
function onChange(file: UploadFile, _files: UploadFiles): void {
  const invalid = validate(file);
  if (invalid) {
    uploadRef.value?.handleRemove(file);
    ElMessage.warning(invalid);
    emit('error', invalid);
    return;
  }
  fileList.value.push({
    name: file.name,
    size: file.size ?? 0,
    status: 'ready',
    percent: 0,
  });
  emit('change', [...fileList.value]);
}

function remove(index: number): void {
  fileList.value.splice(index, 1);
  emit('change', [...fileList.value]);
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<template>
  <div class="lk-file-uploader">
    <el-upload
      ref="uploadRef"
      drag
      :accept="accept"
      :multiple="multiple"
      :disabled="disabled"
      :limit="10"
      :auto-upload="false"
      :show-file-list="false"
      :on-change="onChange"
      :on-exceed="onExceed"
      class="lk-file-uploader__zone"
    >
      <div class="lk-file-uploader__inner">
        <el-icon :size="32" color="var(--lk-color-primary)"><UploadFilled /></el-icon>
        <p class="lk-file-uploader__text">拖拽文件到此处，或<em>点击上传</em></p>
        <p class="lk-file-uploader__tip">{{ tip }}，单个不超过 {{ maxSizeMb }}MB</p>
      </div>
    </el-upload>

    <ul v-if="fileList.length > 0" class="lk-file-uploader__list">
      <li v-for="(item, index) in fileList" :key="item.name" class="lk-file-uploader__item">
        <el-icon><Document /></el-icon>
        <span class="lk-file-uploader__name">{{ item.name }}</span>
        <span class="lk-file-uploader__size">{{ formatSize(item.size) }}</span>
        <el-button text type="danger" @click="remove(index)">移除</el-button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.lk-file-uploader__zone :deep(.el-upload-dragger) {
  padding: var(--lk-space-6);
  background: var(--lk-bg-card);
  border-color: var(--lk-border-color);
  border-radius: var(--lk-radius-component);
}

.lk-file-uploader__inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--lk-space-1);
}

.lk-file-uploader__text {
  margin: var(--lk-space-2) 0 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-secondary);
}

.lk-file-uploader__text em {
  font-style: normal;
  color: var(--lk-color-primary);
}

.lk-file-uploader__tip {
  margin: 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-file-uploader__list {
  margin: var(--lk-space-3) 0 0;
  padding: 0;
  list-style: none;
}

.lk-file-uploader__item {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
  padding: var(--lk-space-2) 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-primary);
  border-bottom: 0.5px solid var(--lk-border-color);
}

.lk-file-uploader__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lk-file-uploader__size {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
