/**
 * config-store 单测：脏标记语义（任一分区改动即整页脏；加载/保存后清除）。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useConfigStore } from '@/features/app/stores/config-store';

const APP = { id: 'app-qingyi', name: '青易ai', type: 'lightweight' as const };

describe('config-store 脏标记', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('初始与加载后均不脏', async () => {
    const store = useConfigStore();
    expect(store.isDirty).toBe(false);
    await store.load('app-qingyi', APP);
    expect(store.isDirty).toBe(false);
    expect(store.app?.name).toBe('青易ai');
  });

  it('任一分区改动即整页脏，reset 后恢复', async () => {
    const store = useConfigStore();
    await store.load('app-qingyi', APP);

    store.update('share', { shareEnabled: false });
    expect(store.isDirty).toBe(true);

    store.reset();
    expect(store.isDirty).toBe(false);
  });

  it('应用基础信息改动也标记脏', async () => {
    const store = useConfigStore();
    await store.load('app-qingyi', APP);

    store.updateAppInfo({ name: '新名字' });
    expect(store.isDirty).toBe(true);
  });
});
