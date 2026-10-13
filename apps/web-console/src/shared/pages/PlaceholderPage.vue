<script setup lang="ts">
/**
 * PlaceholderPage —— 导航占位页（Phase 0）。
 * 对应模块由后续工单以独立 feature 落地；结构保持与正式页一致。
 */
import { useRoute } from 'vue-router';
import { LkAppPage, LkEmptyState } from '@linkai/ui';

const route = useRoute();
const title = (route.meta.title as string | undefined) ?? '模块';
</script>

<template>
  <LkAppPage :title="title" description="该模块由后续工单交付，当前为占位页">
    <LkEmptyState :title="`${title}模块建设中`" description="Phase 0 先落地应用工厂闭环">
      <el-button type="primary" @click="$router.push('/console/factory')">
        返回智能体工厂
      </el-button>
    </LkEmptyState>
  </LkAppPage>
</template>
