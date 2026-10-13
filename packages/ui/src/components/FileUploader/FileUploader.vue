<script setup lang="ts">
/**
 * FileUploader —— 文件上传（docs/04 2.3）：进度 / 类型校验 / 大小超限。
 * 仅做前端校验与列表管理，实际上传由使用方接管 change 事件。
 */
import { ref } from 'vue';
import { ElMessage } from 'element-plus';

export interface UploadFileItem {
  name: string;
  size: number;
  raw?: File;
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

function validate(file: File): string | null {
  const maxBytes = props.maxSizeMb * 1024 * 1024;
  if (file.size > maxBytes) return `「${file.name}」超过 ${props.maxSizeMb}MB 限制`;
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
  const message = `一次最多上传 ${props.multiple ? 10 : 1} 个文件`;
  ElMessage.warning(message);
  emit('error', message);
}

function onChange(file: { raw?: File }, items: { raw?: File; name: string }[]): void {
  const incoming = file.raw;
  if (incoming) {
    const invalid = validate(incoming);
    if (invalid) {
      ElMessage.warning(invalid);
      emit('error', invalid);
      fileList.value = fileList.value.filter((item) => item.name !== incoming.name);
      return;
    }
    fileList.value.push({
      name: incoming.name,
      size: incoming.size,
      raw: incoming,
      status: 'ready',
      percent: 0,
    });
  } else {
    // 移除场景：以组件列表为准同步
    fileList.value = items
      .filter((item) => item.raw)
      .map((item) => ({
        name: item.name,
        size: (item.raw as File).size,
        raw: item.raw,
        status: 'ready' as const,
        percent: 0,
      }));
  }
  emit('change', fileList.value);
}

function remove(index: number): void {
  fileList.value.splice(index, 1);
  emit('change', fileList.value);
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
      drag
      :accept="accept"
      :multiple="multiple"
      :disabled="disabled"
      :limit="10"
      :auto-upload="false"
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
