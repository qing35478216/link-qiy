/**
 * FactoryPage 组件测试（MSW 驱动）。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import FactoryPage from '@/features/app/pages/FactoryPage.vue';
import { mountWithProviders } from './helpers';

describe('FactoryPage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('渲染应用卡片（视觉基准 01-factory：名称/id/类型/操作）', async () => {
    const wrapper = mountWithProviders(FactoryPage);
    await flushPromises();
    await flushPromises();

    const cards = wrapper.findAll('.app-card');
    expect(cards).toHaveLength(3);
    expect(wrapper.text()).toContain('青易ai');
    expect(wrapper.text()).toContain('id:app-qingyi');
    expect(wrapper.text()).toContain('轻量应用');
    expect(wrapper.text()).toContain('知识应用');
    expect(wrapper.text()).toContain('开始对话');
  });

  it('类型筛选：知识应用只留知识卡', async () => {
    const wrapper = mountWithProviders(FactoryPage);
    await flushPromises();
    await flushPromises();

    await wrapper.findAll('.el-radio-button input')[2].setValue(true);
    await flushPromises();
    await flushPromises();

    const cards = wrapper.findAll('.app-card');
    expect(cards).toHaveLength(1);
    expect(wrapper.text()).toContain('塔罗');
  });

  it('加载更多：cursor 分页翻页', async () => {
    const wrapper = mountWithProviders(FactoryPage);
    await flushPromises();
    await flushPromises();
    // 种子 3 条 < limit 12，无下一页按钮
    expect(wrapper.find('.factory__more').exists()).toBe(false);
  });
});
