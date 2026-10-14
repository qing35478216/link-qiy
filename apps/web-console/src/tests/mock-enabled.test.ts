/**
 * mock-enabled 门禁单测（B1 修复回归）：生产默认关、dev/test 默认开、显式变量优先。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { isMockEnabled } from '@/mocks/mock-enabled';

describe('isMockEnabled（MSW 安全默认）', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('生产 + 未设变量 → 关闭（B1 核心回归）', () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('MODE', 'production');
    vi.stubEnv('VITE_ENABLE_MSW', '');
    expect(isMockEnabled()).toBe(false);
  });

  it('开发环境 → 开启', () => {
    vi.stubEnv('DEV', true);
    vi.stubEnv('MODE', 'development');
    vi.stubEnv('VITE_ENABLE_MSW', '');
    expect(isMockEnabled()).toBe(true);
  });

  it('测试环境 → 开启', () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('MODE', 'test');
    vi.stubEnv('VITE_ENABLE_MSW', '');
    expect(isMockEnabled()).toBe(true);
  });

  it('显式 VITE_ENABLE_MSW=true → 生产也开（逃生门）', () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('MODE', 'production');
    vi.stubEnv('VITE_ENABLE_MSW', 'true');
    expect(isMockEnabled()).toBe(true);
  });

  it('显式 VITE_ENABLE_MSW=false → 开发也不开', () => {
    vi.stubEnv('DEV', true);
    vi.stubEnv('MODE', 'development');
    vi.stubEnv('VITE_ENABLE_MSW', 'false');
    expect(isMockEnabled()).toBe(false);
  });
});
