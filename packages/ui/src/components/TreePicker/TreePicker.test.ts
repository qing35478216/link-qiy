import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkTreePicker from './TreePicker.vue';
import type { TreePickerNode } from './TreePicker.vue';

const data: TreePickerNode[] = [
  {
    key: 'root',
    label: '全部知识库',
    children: [
      { key: 'kb-1', label: '产品手册' },
      { key: 'kb-2', label: 'FAQ' },
    ],
  },
];

describe('LkTreePicker', () => {
  it('renders tree nodes and selection count', () => {
    const wrapper = mount(LkTreePicker, { props: { modelValue: ['kb-1'], data } });
    expect(wrapper.find('input').element.value).toBe('已选 1 项');
    expect(wrapper.text()).toContain('全部知识库');
    expect(wrapper.text()).toContain('产品手册');
  });

  it('shows placeholder when nothing selected', () => {
    const wrapper = mount(LkTreePicker, { props: { modelValue: [], data } });
    expect(wrapper.find('input').element.value).toBe('请选择');
  });

  it('emits update:modelValue on check', async () => {
    const wrapper = mount(LkTreePicker, { props: { modelValue: [], data } });
    const tree = wrapper.findComponent({ name: 'ElTree' });
    tree.vm.$emit('check', {}, { checkedKeys: ['kb-1', 'kb-2'] });
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('update:modelValue')).toEqual([[['kb-1', 'kb-2']]]);
    expect(wrapper.emitted('change')).toEqual([[['kb-1', 'kb-2']]]);
  });

  it('disables cascading when folderSelectAll is false', () => {
    const wrapper = mount(LkTreePicker, {
      props: { modelValue: [], data, folderSelectAll: false },
    });
    expect(wrapper.findComponent({ name: 'ElTree' }).props('checkStrictly')).toBe(true);
  });
});
