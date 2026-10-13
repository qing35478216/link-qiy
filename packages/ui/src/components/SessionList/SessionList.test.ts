import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkSessionList from './SessionList.vue';

const sessions = [
  { id: 's1', title: '今天的运势', updatedAt: '10:24', type: 'single' as const },
  { id: 's2', title: '团队周会', updatedAt: '昨天', type: 'group' as const },
];

describe('LkSessionList', () => {
  it('renders sessions and emits select', async () => {
    const wrapper = mount(LkSessionList, { props: { sessions, activeId: 's1' } });
    expect(wrapper.text()).toContain('今天的运势');
    expect(wrapper.find('.lk-session-list__item--active').text()).toContain('今天的运势');
    await wrapper.findAll('.lk-session-list__item')[1].trigger('click');
    expect(wrapper.emitted('select')).toEqual([['s2']]);
  });

  it('filters by keyword', async () => {
    const wrapper = mount(LkSessionList, { props: { sessions } });
    await wrapper.find('input').setValue('周会');
    expect(wrapper.emitted('search')).toEqual([['周会']]);
    expect(wrapper.findAll('.lk-session-list__item')).toHaveLength(1);
  });

  it('filters by tab', async () => {
    const wrapper = mount(LkSessionList, { props: { sessions } });
    await wrapper.findAll('.el-radio-button input')[1].setValue(true);
    expect(wrapper.emitted('tab-change')).toEqual([['group']]);
    expect(wrapper.findAll('.lk-session-list__item')).toHaveLength(1);
  });

  it('emits create', async () => {
    const wrapper = mount(LkSessionList, { props: { sessions } });
    await wrapper.findAll('button')[0].trigger('click');
    expect(wrapper.emitted('create')).toHaveLength(1);
  });

  it('shows empty state', () => {
    const wrapper = mount(LkSessionList, { props: { sessions: [] } });
    expect(wrapper.text()).toContain('暂无会话');
  });
});
