/**
 * mocks/mock-enabled —— MSW 开启门禁（安全默认）。
 *
 * 历史缺陷（B1）：原条件 `VITE_ENABLE_MSW !== 'false'` 在未设环境变量时默认开启，
 * 导致生产 build/preview 也注册 MSW worker、控制台跑夹具数据（任意 ≥4 位验证码即发 token）。
 *
 * 现语义：
 * - 开发（DEV）与测试（MODE=test）默认开启；
 * - 生产默认关闭；
 * - 确需生产开 Mock 时显式设 VITE_ENABLE_MSW=true（逃生门，默认安全）。
 */

/** 是否启用 MSW Mock worker（默认仅 dev/test 开启） */
export function isMockEnabled(): boolean {
  if (import.meta.env.VITE_ENABLE_MSW === 'true') return true;
  if (import.meta.env.VITE_ENABLE_MSW === 'false') return false;
  return import.meta.env.DEV || import.meta.env.MODE === 'test';
}
