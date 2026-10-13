/**
 * mocks/fixtures —— MSW 内存数据（Phase 0 无后端联调期）。
 * 视觉基准：linkai-screenshots/（青易ai / 紫微斗数 / 塔罗 等卡片形态）。
 * 注意：仅 Mock 数据，不构成契约；契约以 packages/contracts 为准。
 */
import type { App, AppConfig, QuotaSummary, UserProfile } from '@linkai/sdk-ts/models/console';

export const MOCK_TENANT_ID = 'tenant-demo-0001';

export interface MockState {
  apps: App[];
  configs: Record<string, AppConfig>;
  nextAppSeq: number;
  quota: QuotaSummary;
  profile: UserProfile;
}

const baseConfig: AppConfig = {
  basic: {
    welcomeMessage: '你好，我是你的专属智能体，有什么可以帮你？',
    guideQuestions: ['你能做什么？', '如何使用知识库？'],
  },
  share: { shareEnabled: true, sharePath: '/app/qingyi', showBranding: false },
  modelPrompt: {
    modelCode: 'gpt-4o',
    systemPrompt: '你是精通太乙神数的专业推演师，回答需给出依据与步骤。',
    temperature: 0.7,
    memoryRounds: 10,
    contextLength: 8000,
    variables: [{ name: 'userName', value: '' }],
  },
  knowledge: {
    datasetIds: [],
    similarityThreshold: 0.8,
    semanticTopK: 5,
    fulltextTopK: 5,
    missStrategy: 'free',
    citationEnabled: true,
  },
  data: { dbDatasetId: '', tableSyncCron: '' },
  plugins: { pluginIds: [], execStrategy: 'parallel', triggerKeywords: [] },
  advanced: { humanTransferEnabled: false, humanizeEnabled: false, rateLimitQpm: 60 },
};

function seedState(): MockState {
  return {
    apps: [
      {
        id: 'app-qingyi',
        name: '青易ai',
        description: '轻易预知未来，太乙神数推演助手',
        type: 'lightweight',
        published: true,
        currentVersion: 3,
        createdAt: '2026-09-01T10:00:00Z',
        updatedAt: '2026-10-10T12:30:00Z',
      },
      {
        id: 'app-ziwei',
        name: '紫微斗数',
        description: '帮助人们了解自身命盘格局与运势走向',
        type: 'lightweight',
        published: false,
        currentVersion: 1,
        createdAt: '2026-09-12T09:20:00Z',
        updatedAt: '2026-09-12T09:20:00Z',
      },
      {
        id: 'app-tarot',
        name: '塔罗',
        description: 'CFTR 用于塔罗牌占卜与解读的知识应用',
        type: 'knowledge',
        published: false,
        currentVersion: 2,
        createdAt: '2026-09-20T15:41:00Z',
        updatedAt: '2026-10-02T08:10:00Z',
      },
    ],
    configs: {
      'app-qingyi': structuredClone(baseConfig),
      'app-ziwei': structuredClone(baseConfig),
      'app-tarot': structuredClone(baseConfig),
    },
    nextAppSeq: 1,
    quota: {
      plan: 'basic',
      planBadge: '基础版',
      walletBalance: 40240,
      upgradeUrl: 'https://link-ai.tech/price',
      usage: { messagesUsed: 120, messagesLimit: 500, tokensUsed: 86000, tokensLimit: 500000 },
    },
    profile: {
      id: 'user-demo',
      nickname: '袁台',
      phone: '138****8888',
      plan: 'basic',
      agreementAcceptedAt: '2026-09-01T09:59:00Z',
    },
  };
}

let state: MockState = seedState();

export function getMockState(): MockState {
  return state;
}

export function resetMockDb(): void {
  state = seedState();
}

/** cursor 分页：按 createdAt 倒序，cursor 为偏移量字符串 */
export function paginateApps(cursor: string | null, limit: number) {
  const apps = [...state.apps].sort((a, b) =>
    String(b.createdAt ?? '').localeCompare(String(a.createdAt ?? '')),
  );
  const offset = cursor ? Number.parseInt(cursor, 10) : 0;
  const safeOffset = Number.isNaN(offset) ? 0 : offset;
  const items = apps.slice(safeOffset, safeOffset + limit);
  const nextOffset = safeOffset + items.length;
  const nextCursor = nextOffset < apps.length ? String(nextOffset) : null;
  return { items, nextCursor };
}

export function createMockApp(input: { name: string; description?: string; type: App['type'] }): App {
  const id = `app-new-${state.nextAppSeq}`;
  state.nextAppSeq += 1;
  const now = new Date().toISOString();
  const app: App = {
    id,
    name: input.name,
    description: input.description,
    type: input.type,
    published: false,
    currentVersion: 0,
    createdAt: now,
    updatedAt: now,
  };
  state.apps.push(app);
  state.configs[id] = structuredClone(baseConfig);
  return app;
}
