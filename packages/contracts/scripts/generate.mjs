#!/usr/bin/env node
/**
 * SDK 生成入口（铁律 8：选型对比见 ADOPTED-TOOLS.md）
 *   sdk-ts: orval（客户端 + 类型 + MSW handlers + TanStack Query hooks）
 *   sdk-py: openapi-python-client（httux + pydantic v2）
 *
 * 用法：node scripts/generate.mjs [--ts] [--py]（缺省全量）
 * 前置：npx 可用（node >= 22，见根 .nvmrc）；openapi-python-client 经 uvx/pipx 调用。
 */
import { execSync } from 'node:child_process';

const only = process.argv.slice(2);
const run = (cmd) => { console.log(`$ ${cmd}`); execSync(cmd, { stdio: 'inherit' }); };
const jobs = {
  ts: () => run('npx -y orval --config orval.config.ts'),
  py: () => run('uvx openapi-python-client generate --path openapi/console-api.yaml --output-path ../sdk-py'),
};

if (only.length === 0) { jobs.ts(); jobs.py(); }
else only.forEach((k) => jobs[k]?.());
console.log('生成完成：packages/sdk-ts（orval 输出）与 packages/sdk-py');
