<script setup lang="ts">
/**
 * FactoryPage —— 应用工厂列表页（视觉基准：linkai-screenshots/01-factory）。
 * cursor 分页（TanStack useInfiniteQuery）+ 类型筛选 + 创建弹窗 + 空状态。
 */
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useInfiniteQuery, useQueryClient } from '@tanstack/vue-query';
import { ElMessage } from 'element-plus';
import {
  LkAppPage,
  LkEmptyState,
  LkFilterBar,
} from '@linkai/ui';
import AppCard from '@/features/app/components/AppCard.vue';
import CreateAppModal from '@/features/app/components/CreateAppModal.vue';
import { createApp, fetchAppsPage } from '@/features/app/api/app-api';
import type { ListAppsType } from '@/types';

const PAGE_SIZE = 12;
const router = useRouter();
const queryClient = useQueryClient();

const typeFilter = ref<ListAppsType>('all');
const createVisible = ref(false);

const appsQuery = useInfiniteQuery({
  queryKey: computed(() => ['apps', typeFilter.value]),
  queryFn: ({ pageParam }) =>
    fetchAppsPage({ limit: PAGE_SIZE, cursor: pageParam, type: typeFilter.value }),
  initialPageParam: undefined as string | undefined,
  getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
});

const apps = computed(() => appsQuery.data.value?.pages.flatMap((page) => page.items) ?? []);
const hasNext = computed(() => Boolean(appsQuery.hasNextPage.value));
const isEmpty = computed(
  () => !appsQuery.isLoading.value && !appsQuery.isError.value && apps.value.length === 0,
);

async function onCreate(payload: { name: string; description?: string; type: 'lightweight' | 'knowledge' }): Promise<void> {
  try {
    const app = await createApp(payload);
    createVisible.value = false;
    ElMessage.success('创建成功，去配置吧');
    await queryClient.invalidateQueries({ queryKey: ['apps'] });
    if (app.id) await router.push(`/console/apps/${app.id}/config`);
  } catch {
    ElMessage.error('创建失败，请重试');
  }
}

function retry(): void {
  void appsQuery.refetch();
}
</script>

<template>
  <LkAppPage title="智能体" description="创建并管理你的智能体应用" :loading="appsQuery.isLoading.value" :error="appsQuery.isError.value ? '应用列表加载失败' : null" @retry="retry">
    <template #actions>
      <el-button type="primary" @click="createVisible = true">创建应用</el-button>
    </template>

    <LkFilterBar>
      <el-radio-group v-model="typeFilter" size="default">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="lightweight">轻量应用</el-radio-button>
        <el-radio-button value="knowledge">知识应用</el-radio-button>
      </el-radio-group>
    </LkFilterBar>

    <LkEmptyState
      v-if="isEmpty"
      title="创建你的第一个智能体"
      description="一段提示词快速创建，或基于私有知识定制问答"
    >
      <el-button type="primary" @click="createVisible = true">创建应用</el-button>
    </LkEmptyState>

    <template v-else>
      <div class="factory__grid">
        <AppCard v-for="app in apps" :key="app.id" :app="app" />
      </div>

      <div v-if="hasNext" class="factory__more">
        <el-button :loading="appsQuery.isFetchingNextPage.value" @click="appsQuery.fetchNextPage()">
          加载更多
        </el-button>
      </div>
    </template>
  </LkAppPage>

  <CreateAppModal v-model="createVisible" @create="onCreate" />
</template>

<style scoped>
.factory__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--lk-space-4);
}

.factory__more {
  display: flex;
  justify-content: center;
  margin-top: var(--lk-space-4);
}

@media (max-width: 1100px) {
  .factory__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
