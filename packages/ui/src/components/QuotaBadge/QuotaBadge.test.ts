import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkQuotaBadge from './QuotaBadge.vue';

describe('LkQuotaBadge', () => {
  it('renders plan badge text', () => {
    const wrapper = mount(LkQuotaBadge, { props: { planBadge: '基础版', plan: 'basic' } });
    expect(wrapper.text()).toContain('基础版');
  });

  it('shows exceeded alert when usage hits limit', async () => {
    const wrapper = mount(LkQuotaBadge, {
      props: {
        planBadge: '基础版',
        plan: 'basic',
        walletBalance: 100,
        usage: { messagesUsed: 100, messagesLimit: 100, tokensUsed: 10, tokensLimit: 1000 },
        upgradeUrl: 'https://example.com/upgrade',
      },
    });
    await wrapper.find('.lk-quota-badge').trigger('click');
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).toContain('已超限');
    expect(document.body.textContent).toContain('100');
    expect(document.body.textContent).toContain('升级版本');
    wrapper.unmount();
  });

  it('emits upgrade', async () => {
    const wrapper = mount(LkQuotaBadge, {
      props: { planBadge: '基础版', upgradeUrl: 'https://example.com/upgrade' },
    });
    await wrapper.find('.lk-quota-badge').trigger('click');
    await wrapper.vm.$nextTick();
    const btn = document.querySelector('.lk-quota-panel__upgrade') as HTMLElement;
    btn.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('upgrade')).toHaveLength(1);
    wrapper.unmount();
  });
});
