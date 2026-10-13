import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkEmptyState from './EmptyState.vue';

describe('LkEmptyState', () => {
  it('renders title, description and CTA slot', () => {
    const wrapper = mount(LkEmptyState, {
      props: { title: '创建你的第一个智能体', description: '一段提示词快速创建' },
      slots: { default: '<button class="cta">创建</button>' },
    });
    expect(wrapper.text()).toContain('创建你的第一个智能体');
    expect(wrapper.text()).toContain('一段提示词快速创建');
    expect(wrapper.find('.cta').exists()).toBe(true);
    expect(wrapper.find('svg').exists()).toBe(true);
  });

  it('renders custom image when provided', () => {
    const wrapper = mount(LkEmptyState, {
      props: { title: 't', image: 'https://example.com/e.png' },
    });
    expect(wrapper.find('img').attributes('src')).toBe('https://example.com/e.png');
    expect(wrapper.find('svg').exists()).toBe(false);
  });
});
