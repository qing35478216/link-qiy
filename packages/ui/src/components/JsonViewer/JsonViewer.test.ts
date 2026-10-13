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
  it('renders top-level entries expanded at expandDepth', () => {
    const wrapper = mount(LkJsonViewer, { props: { data, expandDepth: 1 } });
    expect(wrapper.text()).toContain('modelPrompt');
    expect(wrapper.text()).toContain('{3}');
    // 深度 1 折叠：modelCode 不可见
    expect(wrapper.text()).not.toContain('gpt-4o');
  });

  it('expands deeper levels when expandDepth increases', () => {
    const wrapper = mount(LkJsonViewer, { props: { data, expandDepth: 2 } });
    expect(wrapper.text()).toContain('gpt-4o');
    expect(wrapper.text()).toContain('0.7');
    // 深度 2 仍折叠 variables 内部
    expect(wrapper.text()).not.toContain('张三');
  });

  it('toggles a node on click', async () => {
    const wrapper = mount(LkJsonViewer, { props: { data, expandDepth: 1 } });
    const toggle = wrapper.find('.lk-json-viewer__toggle');
    await toggle.trigger('click');
    expect(wrapper.text()).not.toContain('temperature');
  });

  it('renders primitive root directly', () => {
    const wrapper = mount(LkJsonViewer, { props: { data: 'hello' } });
    expect(wrapper.text()).toContain('"hello"');
  });
});
