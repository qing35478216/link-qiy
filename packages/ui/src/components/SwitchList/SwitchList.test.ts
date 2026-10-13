import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkSwitchList from './SwitchList.vue';

const items = [
  { key: 'vision', label: '图像识别', value: true },
  { key: 'search', label: '谷歌搜索', description: '联网检索', value: false },
];

describe('LkSwitchList', () => {
  it('renders items and emits change', async () => {
    const wrapper = mount(LkSwitchList, { props: { items } });
    expect(wrapper.text()).toContain('图像识别');
    expect(wrapper.text()).toContain('联网检索');
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' });
    switches[1].vm.$emit('update:modelValue', true);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('change')).toEqual([['search', true]]);
  });

  it('shows error with retry', async () => {
    const wrapper = mount(LkSwitchList, { props: { items: [], error: '加载失败' } });
    expect(wrapper.text()).toContain('加载失败');
    await wrapper.find('button').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });

  it('shows empty text', () => {
    const wrapper = mount(LkSwitchList, { props: { items: [], emptyText: '暂无插件' } });
    expect(wrapper.text()).toContain('暂无插件');
  });
});
