import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkDebugDrawer from './DebugDrawer.vue';

describe('LkDebugDrawer', () => {
  it('renders content when visible and emits close', async () => {
    const wrapper = mount(LkDebugDrawer, {
      props: { modelValue: true, title: '对话测试' },
      slots: { default: '<p class="chat">对话测试…</p>' },
      attachTo: document.body,
    });
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).toContain('对话测试');
    expect(document.body.textContent).toContain('对话测试…');
    wrapper.findComponent({ name: 'ElDrawer' }).vm.$emit('close');
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);
    wrapper.unmount();
  });

  it('does not render content when hidden', () => {
    const wrapper = mount(LkDebugDrawer, {
      props: { modelValue: false },
      slots: { default: '<p>隐藏内容</p>' },
    });
    expect(wrapper.text()).not.toContain('隐藏内容');
  });
});
