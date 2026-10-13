<script setup lang="ts">
/**
 * AppConfigPage —— 应用配置页（视觉基准：linkai-screenshots/05-app-config）。
 * 配置七件套：基础/分享/模型+Prompt 落地，知识库/数据/插件/高级占位；
 * 任一分区改动即整页脏标记，保存 = 整页原子保存；未保存离开弹拦截。
 */
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { useQuery } from '@tanstack/vue-query';
import { ElMessage, ElMessageBox } from 'element-plus';
import { LkAppPage, LkDebugDrawer, LkChatWindow } from '@linkai/ui';
import type { ChatWindowMessage } from '@linkai/ui';
import { consoleAPI } from '@/api';
import { useConfigStore } from '@/features/app/stores/config-store';
import BasicInfoSection from '@/features/app/components/BasicInfoSection.vue';
import ShareConfigSection from '@/features/app/components/ShareConfigSection.vue';
import ModelPromptSection from '@/features/app/components/ModelPromptSection.vue';
import PlaceholderSections from '@/features/app/components/PlaceholderSections.vue';

const route = useRoute();
const router = useRouter();
const configStore = useConfigStore();

const appId = computed(() => String(route.params.appId ?? ''));
const debugVisible = ref(false);
const messages = ref<ChatWindowMessage[]>([]);
const streaming = ref(false);

const appQuery = useQuery({
  queryKey: computed(() => ['app', appId.value]),
  queryFn: async () => (await consoleAPI.getApp(appId.value)).data,
  enabled: computed(() => Boolean(appId.value)),
});

onMounted(async () => {
  const app = appQuery.data.value;
  if (app) await configStore.load(appId.value, app);
});

async function onSave(): Promise<void> {
  try {
    const version = await configStore.save();
    ElMessage.success(`已保存（版本 v${version}）`);
  } catch {
    ElMessage.error('保存失败，请重试');
  }
}

function onReset(): void {
  configStore.reset();
}

/** 未保存离开拦截（视觉基准：05-app-config 保存语义） */
onBeforeRouteLeave(async () => {
  if (!configStore.isDirty) return true;
  try {
    await ElMessageBox.confirm('有未保存的配置，离开将丢失修改', '离开确认', { type: 'warning' });
    return true;
  } catch {
    return false;
  }
});

function send(text: string): void {
  messages.value.push({ id: `m-${Date.now()}`, role: 'user', content: text, status: 'done' });
  // Phase 0：本地回显模拟流式，联调期替换为 SSE（runtime-events.yaml）
  streaming.value = true;
  const replyId = `m-${Date.now()}-ai`;
  messages.value.push({ id: replyId, role: 'assistant', content: '', status: 'streaming' });
  const reply = `（Mock 调试）已收到：「${text}」`;
  let index = 0;
  const timer = setInterval(() => {
    const target = messages.value.find((item) => item.id === replyId);
    if (!target) {
      clearInterval(timer);
      return;
    }
    target.content = reply.slice(0, index += 2);
    if (index >= reply.length) {
      target.status = 'done';
      streaming.value = false;
      clearInterval(timer);
    }
  }, 40);
}

function stopStream(): void {
  streaming.value = false;
}
</script>

<template>
  <LkAppPage
    :title="`${configStore.app?.name ?? '应用配置'}`"
    description="配置七件套，整页保存后生效"
    :loading="configStore.loading || appQuery.isLoading.value"
    :error="appQuery.isError.value ? '应用加载失败' : null"
    @retry="appQuery.refetch()"
  >
    <template #actions>
      <el-button :disabled="!configStore.isDirty" @click="onReset">重置</el-button>
      <el-button type="primary" :disabled="!configStore.isDirty" :loading="configStore.saving" @click="onSave">
        保存
      </el-button>
      <el-button @click="debugVisible = true">调试</el-button>
    </template>

    <div class="config-page">
      <BasicInfoSection />
      <ShareConfigSection />
      <ModelPromptSection />
      <PlaceholderSections />
    </div>
  </LkAppPage>

  <LkDebugDrawer v-model="debugVisible" title="对话测试" :width="400">
    <LkChatWindow
      :messages="messages"
      :streaming="streaming"
      :guide-questions="configStore.draft.basic?.guideQuestions ?? []"
      empty-hint="发送一条消息开始调试"
      @send="send"
      @stop="stopStream"
    />
  </LkDebugDrawer>
</template>

<style scoped>
.config-page {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-4);
}
</style>
