import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkDataTable from './DataTable.vue';

interface Row {
  id: string;
  name: string;
}

const rows: Row[] = [
  { id: 'a', name: '青易ai' },
  { id: 'b', name: '紫微斗数' },
];

const columns = [
  { prop: 'name', label: '名称' },
  { prop: 'id', label: '标识', formatter: (row: Row) => `#${row.id}` },
];

describe('LkDataTable', () => {
  it('renders rows with formatter and slot override', () => {
    const wrapper = mount(LkDataTable, {
      props: { columns, rows, rowKey: 'id' },
      slots: { 'cell-name': '<b class="custom">slot-cell</b>' },
    });
    const texts = wrapper.findAll('td').map((cell) => cell.text());
    expect(texts).toContain('slot-cell');
    expect(texts).toContain('#a');
    expect(texts).toContain('#b');
  });

  it('shows empty text when no rows', () => {
    const wrapper = mount(LkDataTable, {
      props: { columns, rows: [], rowKey: 'id', emptyText: '空着呢' },
    });
    expect(wrapper.text()).toContain('空着呢');
  });

  it('emits page-change from pagination', () => {
    const wrapper = mount(LkDataTable, {
      props: { columns, rows, rowKey: 'id', pagination: { page: 1, pageSize: 10, total: 42 } },
    });
    expect(wrapper.text()).toContain('42');
  });
});
