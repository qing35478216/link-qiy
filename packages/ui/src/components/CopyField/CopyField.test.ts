import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import LkCopyField from './CopyField.vue';

describe('LkCopyField', () => {
  it('renders readonly value with label', () => {
    const wrapper = mount(LkCopyField, {
      props: { modelValue: 'https://link.ai/app/abc', label: '专属链接' },
    });
    expect(wrapper.find('input').element.value).toBe('https://link.ai/app/abc');
    expect(wrapper.text()).toContain('专属链接');
  });

  it('copies to clipboard and shows success feedback', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const wrapper = mount(LkCopyField, { props: { modelValue: 'sk-123' } });
    await wrapper.find('.lk-copy-field__button').trigger('click');
    expect(writeText).toHaveBeenCalledWith('sk-123');
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.lk-copy-field__button').text()).toBe('已复制');
  });
});
