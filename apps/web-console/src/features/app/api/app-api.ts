/**
 * features/app/api —— 应用工厂数据访问（薄封装，全部走 sdk-ts 生成客户端）。
 *
 * 说明：契约 /apps 列表响应为通用 Page（items 为 object 数组，无具体形态），
 * 此处用运行时守卫把 items 收窄为契约 App 类型——类型仍全部来自生成物。
 */
import { consoleAPI } from '@/api';
import type { App, AppConfig, ListApps200, ListAppsParams } from '@linkai/sdk-ts/console';

export type AppsPage = {
  items: App[];
  nextCursor: string | null;
};

/** 运行时收窄：通用 object → 契约 App（校验 name/type 必填项） */
export function narrowApps(items: ListApps200['items']): App[] {
  const apps: App[] = [];
  for (const item of items) {
    const record = item;
    const name = record.name;
    const type = record.type;
    if (typeof name !== 'string') continue;
    if (type !== 'lightweight' && type !== 'knowledge') continue;
    apps.push({
      name,
      type,
      ...(typeof record.id === 'string' ? { id: record.id } : {}),
      ...(typeof record.description === 'string' ? { description: record.description } : {}),
      ...(typeof record.iconUrl === 'string' ? { iconUrl: record.iconUrl } : {}),
      ...(typeof record.published === 'boolean' ? { published: record.published } : {}),
      ...(typeof record.currentVersion === 'number' ? { currentVersion: record.currentVersion } : {}),
      ...(typeof record.createdAt === 'string' ? { createdAt: record.createdAt } : {}),
      ...(typeof record.updatedAt === 'string' ? { updatedAt: record.updatedAt } : {}),
    });
  }
  return apps;
}

export async function fetchAppsPage(params?: ListAppsParams): Promise<AppsPage> {
  const response = await consoleAPI.listApps(params);
  return { items: narrowApps(response.data.items), nextCursor: response.data.nextCursor };
}

export async function createApp(input: {
  name: string;
  description?: string;
  type: App['type'];
}): Promise<App> {
  const response = await consoleAPI.createApp(input);
  return response.data;
}

export async function fetchAppConfig(appId: string): Promise<AppConfig> {
  const response = await consoleAPI.getAppConfig(appId);
  return response.data;
}

export async function saveAppConfig(appId: string, config: AppConfig): Promise<number> {
  const response = await consoleAPI.putAppConfig(appId, config);
  return response.data.version ?? 0;
}

export async function updateAppBasic(
  appId: string,
  patch: Pick<App, 'name' | 'description' | 'type' | 'iconUrl'>,
): Promise<App> {
  const response = await consoleAPI.updateApp(appId, patch);
  return response.data;
}

export async function deleteApp(appId: string): Promise<void> {
  await consoleAPI.deleteApp(appId);
}
