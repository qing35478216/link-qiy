<script setup lang="ts">
/**
 * JsonNodeView —— JsonViewer 的递归节点：容器可折叠，叶子直接渲染。
 */
import { computed, ref } from 'vue';

const props = defineProps<{
  nodeKey: string;
  value: unknown;
  depth: number;
  expandDepth: number;
}>();

// 展开深度语义：expandDepth = 展开的容器层数，顶层键算第 1 层。
// depth <= expandDepth 的容器默认展开，故 expandDepth=1 只见顶层键的直接子级，
// expandDepth=2 再展开 variables 这类二级容器（其内部叶子才可见）。
const open = ref(props.depth <= props.expandDepth);

function isContainer(value: unknown): boolean {
  return typeof value === 'object' && value !== null;
}

function entriesOf(value: unknown): [string, unknown][] {
  if (Array.isArray(value)) return value.map((item, index) => [String(index), item]);
  return Object.entries(value as Record<string, unknown>);
}

const entries = computed(() => entriesOf(props.value));

const summary = computed(() =>
  Array.isArray(props.value) ? `[${entries.value.length}]` : `{${entries.value.length}}`,
);

function formatPrimitive(value: unknown): string {
  if (typeof value === 'string') return `"${value}"`;
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  return String(value);
}
</script>

<template>
  <span v-if="!isContainer(value)" class="lk-json-node__primitive">
    <span class="lk-json-node__key">{{ nodeKey }}: </span>{{ formatPrimitive(value) }}
  </span>
  <div v-else class="lk-json-node">
    <span class="lk-json-node__toggle" @click="open = !open">
      <span class="lk-json-node__arrow">{{ open ? '▼' : '▶' }}</span>
      <span class="lk-json-node__key">{{ nodeKey }}: </span>
      <span class="lk-json-node__summary">{{ summary }}</span>
    </span>
    <ul v-if="open" class="lk-json-node__list">
      <li v-for="[key, child] in entries" :key="key">
        <JsonNodeView :node-key="key" :value="child" :depth="depth + 1" :expand-depth="expandDepth" />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.lk-json-node__list {
  margin: 0;
  padding-left: var(--lk-space-4);
  list-style: none;
}

.lk-json-node__toggle {
  cursor: pointer;
}

.lk-json-node__arrow {
  display: inline-block;
  width: 14px;
  color: var(--lk-text-weak);
}

.lk-json-node__key {
  color: var(--lk-text-primary);
}

.lk-json-node__summary {
  color: var(--lk-text-weak);
}

.lk-json-node__primitive {
  color: var(--lk-text-secondary);
}
</style>
