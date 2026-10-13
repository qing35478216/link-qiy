import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkConfigSection from './ConfigSection.vue';

describe('LkConfigSection', () => {
  it('renders title, description, body and footer slots', () => {
    const wrapper = mount(LkConfigSection, {
      props: { title: '模型设置', description: '默认模型与采样参数' },
      slots: { default: '<input class="f" />', footer: '<span>保存后生效</span>' },
    });
    expect(wrapper.text()).toContain('模型设置');
    expect(wrapper.text()).toContain('默认模型与采样参数');
    expect(wrapper.find('.f').exists()).toBe(true);
    expect(wrapper.text()).toContain('保存后生效');
  });

  it('shows dirty marker when dirty', () => {
    const wrapper = mount(LkConfigSection, { props: { title: 'x', dirty: true } });
    expect(wrapper.find('.lk-config-section__dirty').exists()).toBe(true);
  });

  it('collapses body when collapsible and toggled', async () => {
    const wrapper = mount(LkConfigSection, {
      props: { title: 'x', collapsible: true },
      slots: { default: '<input class="f" />' },
    });
    const body = wrapper.find('.lk-config-section__body');
    expect(body.isVisible()).toBe(true);
    await wrapper.find('.lk-config-section__collapse').trigger('click');
    expect(body.isVisible()).toBe(false);
  });
});
