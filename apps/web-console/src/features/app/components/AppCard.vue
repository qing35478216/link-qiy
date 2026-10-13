<script setup lang="ts">
/**
 * AppCard —— 应用工厂卡片（视觉基准：linkai-screenshots/01-factory）。
 * 契约 App 无 code 字段，标识位以 id 等宽小字呈现。
 */
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import type { App } from '@/types';

const props = defineProps<{
  app: App;
}>();

const router = useRouter();

const initial = computed(() => props.app.name.slice(0, 1));
const typeLabel = computed(() => (props.app.type === 'knowledge' ? '知识应用' : '轻量应用'));

function openConfig(): void {
  if (props.app.id) void router.push(`/console/apps/${props.app.id}/config`);
}

function openChat(): void {
  if (props.app.id) void router.push(`/console/apps/${props.app.id}/chat`);
}

async function copyShareLink(): Promise<void> {
  const link = `${globalThis.location.origin}/app/${props.app.id ?? ''}`;
  try {
    await navigator.clipboard.writeText(link);
    ElMessage.success('分享链接已复制');
  } catch {
    ElMessage.warning('复制失败，请手动复制');
  }
}
</script>

<template>
  <article class="app-card">
    <header class="app-card__header">
      <div class="app-card__avatar">
        <img v-if="app.iconUrl" :src="app.iconUrl" :alt="app.name" />
        <span v-else>{{ initial }}</span>
      </div>
      <div class="app-card__heading">
        <h3 class="app-card__name">{{ app.name }}</h3>
        <p class="app-card__id">id:{{ app.id }}</p>
      </div>
    </header>

    <p class="app-card__description">{{ app.description || '暂无描述' }}</p>

    <footer class="app-card__footer">
      <span class="app-card__type" :class="`app-card__type--${app.type}`">{{ typeLabel }}</span>
      <div class="app-card__actions">
        <el-button type="primary" size="small" round @click="openChat">开始对话</el-button>
        <el-tooltip content="设置" placement="top">
          <el-button size="small" circle @click="openConfig">
            <el-icon><Setting /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="分享" placement="top">
          <el-button size="small" circle @click="copyShareLink">
            <el-icon><Share /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </footer>
  </article>
</template>

<style scoped>
.app-card {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-3);
  padding: var(--lk-space-4);
  background: var(--lk-bg-card);
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-card);
  transition: box-shadow var(--lk-transition-fast);
}

.app-card:hover {
  box-shadow: var(--lk-shadow-float);
}

.app-card__header {
  display: flex;
  align-items: center;
  gap: var(--lk-space-3);
}

.app-card__avatar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  overflow: hidden;
  font-size: var(--lk-font-size-md);
  font-weight: 600;
  color: var(--lk-text-inverse);
  background: var(--lk-color-primary);
  border-radius: var(--lk-radius-round);
}

.app-card__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.app-card__heading {
  min-width: 0;
}

.app-card__name {
  margin: 0;
  font-size: var(--lk-font-size-md);
  font-weight: 600;
  color: var(--lk-text-primary);
}

.app-card__id {
  margin: 2px 0 0;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-card__description {
  display: -webkit-box;
  overflow: hidden;
  margin: 0;
  font-size: var(--lk-font-size-xs);
  line-height: 1.6;
  color: var(--lk-text-secondary);
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.app-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lk-space-2);
}

.app-card__type {
  padding: 1px var(--lk-space-2);
  font-size: var(--lk-font-size-xs);
  border-radius: var(--lk-radius-round);
}

.app-card__type--lightweight {
  color: var(--lk-color-primary);
  background: var(--lk-color-primary-bg);
}

.app-card__type--knowledge {
  color: var(--lk-color-purple);
  background: var(--lk-color-purple-bg);
}

.app-card__actions {
  display: flex;
  gap: var(--lk-space-1);
}
</style>
