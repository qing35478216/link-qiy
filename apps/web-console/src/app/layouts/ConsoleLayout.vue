/**
 * ConsoleLayout —— 控制台外壳：侧边栏（四组导航，220px 可折叠）+ 顶栏 + 内容区。
 * 视觉基准：linkai-screenshots/01-factory-智能体.png；内容区最大宽度 1200px 居中。
 */
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import AppSidebar from './AppSidebar.vue';
import AppTopbar from './AppTopbar.vue';

const collapsed = ref(false);
const route = useRoute();

const breadcrumb = computed(() => {
  const trail = route.meta.breadcrumb;
  return Array.isArray(trail) ? (trail as string[]) : [];
});
</script>

<template>
  <div class="console-layout" :class="{ 'console-layout--collapsed': collapsed }">
    <AppSidebar v-model:collapsed="collapsed" />
    <div class="console-layout__main">
      <AppTopbar />
      <nav v-if="breadcrumb.length > 0" class="console-layout__breadcrumb">
        <span
          v-for="(item, index) in breadcrumb"
          :key="item"
          class="console-layout__crumb"
        >
          <span v-if="index > 0" class="console-layout__separator">/</span>
          {{ item }}
        </span>
      </nav>
      <main class="console-layout__content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.console-layout {
  display: flex;
  min-height: 100vh;
  background: var(--lk-bg-page);
}

.console-layout__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.console-layout__breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--lk-space-1);
  padding: var(--lk-space-3) var(--lk-space-6) 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.console-layout__separator {
  margin-right: var(--lk-space-1);
}

.console-layout__content {
  flex: 1;
  width: 100%;
  max-width: var(--lk-content-max-width);
  margin: 0 auto;
  padding: var(--lk-space-4) var(--lk-space-6) var(--lk-space-8);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--lk-transition-fast);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
