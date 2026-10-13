import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkAppPage from './AppPage.vue';

describe('LkAppPage', () => {
  it('renders title, description and actions slot', () => {
    const wrapper = mount(LkAppPage, {
      props: { title: '智能体', description: '管理你的智能体应用' },
      slots: { actions: '<button class="act">创建</button>', default: '<p class="body">内容</p>' },
    });
    expect(wrapper.text()).toContain('智能体');
    expect(wrapper.text()).toContain('管理你的智能体应用');
    expect(wrapper.find('.act').exists()).toBe(true);
    expect(wrapper.find('.body').exists()).toBe(true);
  });

  it('shows error alert with retry and hides body content when error', async () => {
    const wrapper = mount(LkAppPage, {
      props: { title: '智能体', error: '加载失败' },
      slots: { default: '<p class="body">内容</p>' },
    });
    expect(wrapper.text()).toContain('加载失败');
    await wrapper.find('.lk-app-page__retry').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });

  it('applies loading state', () => {
    const wrapper = mount(LkAppPage, { props: { title: 'x', loading: true } });
    expect(wrapper.find('.el-loading-mask').exists()).toBe(true);
  });
});
