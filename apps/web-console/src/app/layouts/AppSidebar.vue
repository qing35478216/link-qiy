<script setup lang="ts">
/**
 * AppSidebar —— 侧边栏四组导航（el-menu router 模式，分组折叠）。
 */
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { NAV_GROUPS } from '@/app/router/nav-config';

const props = defineProps<{
  collapsed: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:collapsed', collapsed: boolean): void;
}>();

const route = useRoute();
const activeKey = computed(() => (route.meta.navKey as string | undefined) ?? 'factory');

function toggle(): void {
  emit('update:collapsed', !props.collapsed);
}
</script>

<template>
  <aside class="app-sidebar" :class="{ 'app-sidebar--collapsed': collapsed }">
    <div class="app-sidebar__logo">
      <span class="app-sidebar__logo-mark">L</span>
      <span v-show="!collapsed" class="app-sidebar__logo-text">Link.AI</span>
    </div>

    <el-menu
      :default-active="activeKey"
      :collapse="collapsed"
      :collapse-transition="false"
      router
      class="app-sidebar__menu"
    >
      <el-sub-menu v-for="group in NAV_GROUPS" :key="group.key" :index="group.key">
        <template #title>
          <span class="app-sidebar__group-label">{{ group.label }}</span>
        </template>
        <el-menu-item
          v-for="item in group.items"
          :key="item.key"
          :index="item.key"
          :route="{ path: item.route }"
        >
          <span class="app-sidebar__item-label">{{ item.label }}</span>
        </el-menu-item>
      </el-sub-menu>
    </el-menu>

    <button class="app-sidebar__collapse" type="button" @click="toggle">
      {{ collapsed ? '»' : '«' }}
    </button>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  width: var(--lk-sidebar-width);
  height: 100vh;
  background: var(--lk-bg-card);
  border-right: 0.5px solid var(--lk-border-color);
  transition: width var(--lk-transition-base);
}

.app-sidebar--collapsed {
  width: var(--lk-sidebar-width-collapsed);
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--lk-space-2);
  height: var(--lk-topbar-height);
  padding: 0 var(--lk-space-4);
  border-bottom: 0.5px solid var(--lk-border-color);
}

.app-sidebar__logo-mark {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: var(--lk-font-size-md);
  font-weight: 700;
  color: var(--lk-text-inverse);
  background: var(--lk-color-primary);
  border-radius: var(--lk-radius-component);
}

.app-sidebar__logo-text {
  font-size: var(--lk-font-size-md);
  font-weight: 600;
  color: var(--lk-text-primary);
  white-space: nowrap;
}

.app-sidebar__menu {
  flex: 1;
  overflow-y: auto;
  border-right: none;
  background: transparent;
}

.app-sidebar__group-label {
  font-size: var(--lk-font-size-xs);
  font-weight: 600;
  color: var(--lk-text-weak);
}

.app-sidebar__collapse {
  padding: var(--lk-space-2);
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-weak);
  background: transparent;
  border: none;
  border-top: 0.5px solid var(--lk-border-color);
  cursor: pointer;
}

.app-sidebar__collapse:hover {
  color: var(--lk-color-primary);
  background: var(--lk-bg-hover);
}
</style>
