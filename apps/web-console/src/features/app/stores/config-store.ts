/**
 * features/app/stores/config-store —— 配置七件套草稿态。
 * 语义（docs/04 3.1）：任一分区改动即整页脏标记；保存 = 整页原子保存
 * （基础信息 PATCH /apps/:id + 七件套 PUT /apps/:id/config，契约无单接口）。
 */
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { Ref } from 'vue';
import type { App, AppConfig } from '@/types';

/** 深拷贝：契约数据均为 JSON 结构；structuredClone 无法处理 reactive proxy（DataCloneError） */
function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
import {
  fetchAppConfig,
  saveAppConfig,
  updateAppBasic,
} from '@/features/app/api/app-api';

export const useConfigStore = defineStore('app-config', () => {
  const app = ref<App | null>(null);
  const savedApp = ref<App | null>(null);
  const draft = ref<AppConfig>({});
  const saved = ref<AppConfig>({});
  const loading = ref(false);
  const saving = ref(false);

  const isDirty = computed(
    () =>
      JSON.stringify(draft.value) !== JSON.stringify(saved.value) ||
      JSON.stringify(app.value) !== JSON.stringify(savedApp.value),
  );

  async function load(appId: string, appInfo: App): Promise<void> {
    loading.value = true;
    try {
      const config = await fetchAppConfig(appId);
      app.value = appInfo;
      savedApp.value = deepClone(appInfo);
      draft.value = deepClone(config);
      saved.value = deepClone(config);
    } finally {
      loading.value = false;
    }
  }

  function update<K extends keyof AppConfig>(section: K, patch: Partial<NonNullable<AppConfig[K]>>): void {
    const current = draft.value[section] ?? {};
    draft.value = { ...draft.value, [section]: { ...current, ...patch } };
  }

  function updateAppInfo(patch: Partial<App>): void {
    if (app.value) app.value = { ...app.value, ...patch };
  }

  /** 整页原子保存：先基础信息（App），后七件套（AppConfig） */
  async function save(): Promise<number> {
    if (!app.value?.id) throw new Error('config store not loaded');
    saving.value = true;
    try {
      await updateAppBasic(app.value.id, {
        name: app.value.name,
        description: app.value.description,
        type: app.value.type,
        ...(app.value.iconUrl ? { iconUrl: app.value.iconUrl } : {}),
      });
      const version = await saveAppConfig(app.value.id, draft.value);
      saved.value = deepClone(draft.value);
      savedApp.value = deepClone(app.value);
      return version;
    } finally {
      saving.value = false;
    }
  }

  function reset(): void {
    if (saved.value) draft.value = deepClone(saved.value);
    if (savedApp.value) app.value = deepClone(savedApp.value);
  }

  function clear(): void {
    app.value = null;
    savedApp.value = null;
    draft.value = {};
    saved.value = {};
  }

  return {
    app,
    draft: draft as Ref<AppConfig>,
    saved,
    loading,
    saving,
    isDirty,
    load,
    update,
    updateAppInfo,
    save,
    reset,
    clear,
  };
});
