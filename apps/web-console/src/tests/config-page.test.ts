/**
 * AppConfigPage 组件测试：配置七件套加载 → 脏标记 → 整页保存（MSW 驱动）。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createRouter, createWebHistory } from 'vue-router';
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query';
import AppConfigPage from '@/features/app/pages/AppConfigPage.vue';

function mountConfigPage() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      {
        path: '/console/apps/:appId/config',
        name: 'app-config',
        component: AppConfigPage,
      },
    ],
  });
  void router.push('/console/apps/app-qingyi/config');
  void router.isReady();
  return mount(AppConfigPage, {
    global: {
      plugins: [pinia, router, [VueQueryPlugin, { queryClient: new QueryClient() }]],
    },
  });
}

describe('AppConfigPage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('加载配置七件套：基础/分享/模型/占位分区齐全', async () => {
    const wrapper = mountConfigPage();
    await flushPromises();
    await flushPromises();
    await flushPromises();

    expect(wrapper.text()).toContain('基础信息');
    expect(wrapper.text()).toContain('应用分享');
    expect(wrapper.text()).toContain('模型设置');
    expect(wrapper.text()).toContain('应用设定');
    expect(wrapper.text()).toContain('知识库配置');
    expect(wrapper.text()).toContain('插件配置');
    expect(wrapper.text()).toContain('高级配置');
    expect(wrapper.find('input[placeholder="请输入应用名称"]').element.value).toBeTruthy();
  });

  it('任一分区改动即整页脏标记，保存后清除', async () => {
    const wrapper = mountConfigPage();
    await flushPromises();
    await flushPromises();
    await flushPromises();

    const saveBtn = () =>
      wrapper.findAll('button').find((btn) => btn.text() === '保存')!;
    expect(saveBtn().attributes('disabled')).toBeDefined();

    // 改动「应用设定」提示词
    const textarea = wrapper.find('textarea');
    await textarea.setValue('你是精通六爻的推演师');
    await flushPromises();

    expect(saveBtn().attributes('disabled')).toBeUndefined();
    await saveBtn().trigger('click');
    await flushPromises();
    await flushPromises();
    await flushPromises();

    expect(saveBtn().attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('已保存');
  });

  it('调试抽屉可打开', async () => {
    const wrapper = mountConfigPage();
    await flushPromises();
    await flushPromises();

    await wrapper.findAll('button').find((btn) => btn.text() === '调试')!.trigger('click');
    await flushPromises();
    expect(document.body.textContent).toContain('对话测试');
    wrapper.unmount();
  });
});
