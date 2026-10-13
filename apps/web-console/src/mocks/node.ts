/**
 * mocks/node —— 测试环境 MSW server（拦截 fetch adapter 请求）。
 */
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
