<script setup lang="ts">
/**
 * JsonViewer —— JSON/变量查看（docs/04 2.3）：可折叠树，默认展开 expandDepth 层。
 */
import { computed, ref } from 'vue';
import JsonNodeView from './JsonNodeView.vue';

const props = withDefaults(
  defineProps<{
    data: unknown;
    expandDepth?: number;
    copyable?: boolean;
  }>(),
  { expandDepth: 1, copyable: false },
);

const copied = ref(false);

function isContainer(value: unknown): boolean {
  return typeof value === 'object' && value !== null;
}

function rootEntries(): [string, unknown][] {
  const { data } = props;
  if (Array.isArray(data)) return data.map((item, index) => [String(index), item]);
  if (isContainer(data)) return Object.entries(data as Record<string, unknown>);
  return [];
}

const entries = computed(rootEntries);

function formatPrimitive(value: unknown): string {
  if (typeof value === 'string') return `"${value}"`;
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  return String(value);
}
</script>

<template>
  <div class="lk-json-viewer">
    <div v-if="copyable" class="lk-json-viewer__toolbar">
      <span class="lk-json-viewer__copy" @click="copied = true">{{ copied ? '已复制' : '复制' }}</span>
    </div>
    <div class="lk-json-viewer__tree">
      <span v-if="!isContainer(data)" class="lk-json-viewer__primitive">{{ formatPrimitive(data) }}</span>
      <ul v-else class="lk-json-viewer__list">
        <li v-for="[key, value] in entries" :key="key">
          <!-- 顶层条目 depth=0：expandDepth=1 时顶层展开，逐层加深展开更多 -->
          <JsonNodeView :node-key="key" :value="value" :depth="0" :expand-depth="expandDepth" />
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.lk-json-viewer {
  padding: var(--lk-space-3);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: var(--lk-font-size-xs);
  line-height: 1.8;
  background: var(--lk-bg-card);
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-component);
}

.lk-json-viewer__toolbar {
  display: flex;
  justify-content: flex-end;
}

.lk-json-viewer__copy {
  color: var(--lk-color-primary);
  cursor: pointer;
}

.lk-json-viewer__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.lk-json-viewer__primitive {
  color: var(--lk-text-secondary);
}
</style>
