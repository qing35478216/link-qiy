<script setup lang="ts">
/**
 * SessionList —— 会话列表（docs/04 2.3）：Tab / 搜索 / 空。
 */
import { computed, ref } from 'vue';

export type SessionListTab = 'all' | 'group' | 'single' | 'app';

export interface SessionListItem {
  id: string;
  title: string;
  updatedAt?: string;
  type: SessionListTab;
}

const props = withDefaults(
  defineProps<{
    sessions: SessionListItem[];
    activeId?: string;
    tabs?: SessionListTab[];
  }>(),
  { tabs: () => ['all', 'group', 'single', 'app'] },
);

const emit = defineEmits<{
  (e: 'select', id: string): void;
  (e: 'create'): void;
  (e: 'search', keyword: string): void;
  (e: 'tab-change', tab: SessionListTab): void;
}>();

const TAB_LABELS: Record<SessionListTab, string> = {
  all: '全部',
  group: '群聊',
  single: '单聊',
  app: '应用',
};

const keyword = ref('');
const activeTab = ref<SessionListTab>('all');

const filtered = computed(() => {
  const byTab = props.sessions.filter(
    (session) => activeTab.value === 'all' || session.type === activeTab.value,
  );
  if (!keyword.value) return byTab;
  return byTab.filter((session) => session.title.includes(keyword.value));
});

function onSearch(): void {
  emit('search', keyword.value);
}
</script>

<template>
  <div class="lk-session-list">
    <div class="lk-session-list__header">
      <el-input
        v-model="keyword"
        placeholder="搜索会话"
        clearable
        size="small"
        @input="onSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button size="small" type="primary" @click="emit('create')">新建</el-button>
    </div>

    <el-radio-group v-model="activeTab" size="small" @change="(tab: SessionListTab) => emit('tab-change', tab)">
      <el-radio-button v-for="tab in tabs" :key="tab" :value="tab">
        {{ TAB_LABELS[tab] }}
      </el-radio-button>
    </el-radio-group>

    <p v-if="filtered.length === 0" class="lk-session-list__empty">暂无会话</p>

    <ul v-else class="lk-session-list__items">
      <li
        v-for="session in filtered"
        :key="session.id"
        class="lk-session-list__item"
        :class="{ 'lk-session-list__item--active': session.id === activeId }"
        @click="emit('select', session.id)"
      >
        <span class="lk-session-list__title">{{ session.title }}</span>
        <span v-if="session.updatedAt" class="lk-session-list__time">{{ session.updatedAt }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.lk-session-list {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-3);
  height: 100%;
}

.lk-session-list__header {
  display: flex;
  gap: var(--lk-space-2);
}

.lk-session-list__empty {
  margin: 0;
  padding: var(--lk-space-6) 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
  text-align: center;
}

.lk-session-list__items {
  flex: 1;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.lk-session-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lk-space-2);
  padding: var(--lk-space-2) var(--lk-space-3);
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-primary);
  border-radius: var(--lk-radius-component);
  cursor: pointer;
}

.lk-session-list__item:hover {
  background: var(--lk-bg-hover);
}

.lk-session-list__item--active {
  color: var(--lk-color-primary);
  background: var(--lk-color-primary-bg);
}

.lk-session-list__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lk-session-list__time {
  flex-shrink: 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}
</style>
