import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkVersionGate from './VersionGate.vue';

describe('LkVersionGate', () => {
  it('renders slot when plan is sufficient', () => {
    const wrapper = mount(LkVersionGate, {
      props: { currentPlan: 'pro', requiredPlan: 'standard' },
      slots: { default: '<p class="feature">高级功能</p>' },
    });
    expect(wrapper.find('.feature').exists()).toBe(true);
    expect(wrapper.text()).not.toContain('需要更高版本');
  });

  it('blocks content and shows upgrade guide when plan is insufficient', async () => {
    const wrapper = mount(LkVersionGate, {
      props: { currentPlan: 'basic', requiredPlan: 'pro', featureName: '团队空间' },
      slots: { default: '<p class="feature">高级功能</p>' },
    });
    expect(wrapper.find('.feature').exists()).toBe(false);
    expect(wrapper.text()).toContain('团队空间需要更高版本');
    await wrapper.find('button').trigger('click');
    expect(wrapper.emitted('upgrade')).toHaveLength(1);
  });
});
