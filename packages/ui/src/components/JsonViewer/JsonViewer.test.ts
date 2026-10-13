import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkJsonViewer from './JsonViewer.vue';

const data = {
  modelPrompt: {
    modelCode: 'gpt-4o',
    temperature: 0.7,
    variables: [{ name: 'userName', value: '张三' }],
  },
  share: { shareEnabled: true },
};

describe('LkJsonViewer', () => {
  it('renders top-level entries with their immediate children at expandDepth 1', () => {
    const wrapper = mount(LkJsonViewer, { props: { data, expandDepth: 1 } });
    expect(wrapper.text()).toContain('modelPrompt');
    expect(wrapper.text()).toContain('{3}');
    // 深度 1：二级容器（variables）折叠，其子级不可见
    expect(wrapper.text()).toContain('gpt-4o');
    expect(wrapper.text()).not.toContain('张三');
  });

  it('opens one more level per expandDepth step', () => {
    // 语义（JsonNodeView）：depth <= expandDepth 的容器默认展开
    const depth1 = mount(LkJsonViewer, { props: { data, expandDepth: 1 } });
    expect(depth1.text()).toContain('gpt-4o');
    // 深度 2 的数组元素容器仍折叠
    expect(depth1.text()).not.toContain('张三');

    const depth2 = mount(LkJsonViewer, { props: { data, expandDepth: 2 } });
    expect(depth2.text()).toContain('variables');
    expect(depth2.text()).toContain('张三');
  });

  it('toggles a node on click', async () => {
    const wrapper = mount(LkJsonViewer, { props: { data, expandDepth: 1 } });
    expect(wrapper.text()).toContain('temperature');
    await wrapper.find('.lk-json-node__toggle').trigger('click');
    expect(wrapper.text()).not.toContain('temperature');
  });

  it('renders primitive root directly', () => {
    const wrapper = mount(LkJsonViewer, { props: { data: 'hello' } });
    expect(wrapper.text()).toContain('"hello"');
  });
});
