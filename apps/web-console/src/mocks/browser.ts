/**
 * mocks/browser —— 开发环境 MSW service worker。
 * worker 脚本位于 public/mockServiceWorker.js（msw 包内拷贝）。
 */
import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

const worker = setupWorker(...handlers);

export async function startMockWorker(): Promise<void> {
  await worker.start({
    onUnhandledRequest: 'warn',
    quiet: true,
  });
}
