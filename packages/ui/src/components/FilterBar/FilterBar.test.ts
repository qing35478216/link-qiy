import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkFilterBar from './FilterBar.vue';

describe('LkFilterBar', () => {
  it('renders filters and actions slots', () => {
    const wrapper = mount(LkFilterBar, {
      slots: { default: '<input class="f1" /><input class="f2" />', actions: '<button>查询</button>' },
    });
    expect(wrapper.find('.f1').exists()).toBe(true);
    expect(wrapper.text()).toContain('查询');
  });

  it('emits reset', async () => {
    const wrapper = mount(LkFilterBar, { slots: { default: '<input />' } });
    await wrapper.findAll('button').find((b) => b.text() === '重置')!.trigger('click');
    expect(wrapper.emitted('reset')).toHaveLength(1);
  });

  it('toggles collapse state and emits update:collapsed', async () => {
    const wrapper = mount(LkFilterBar, {
      slots: { default: '<input class="f1" /><input class="f2" />' },
    });
    const toggleBtn = wrapper.findAll('button').find((b) => b.text().includes('收起'))!;
    await toggleBtn.trigger('click');
    expect(wrapper.emitted('update:collapsed')).toEqual([[true]]);
    expect(wrapper.find('.lk-filter-bar').classes()).toContain('lk-filter-bar--collapsed');
    await wrapper.findAll('button').find((b) => b.text().includes('展开'))!.trigger('click');
    expect(wrapper.emitted('update:collapsed')).toEqual([[true], [false]]);
  });
});
