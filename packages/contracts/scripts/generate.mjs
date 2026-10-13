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
import { mkdirSync } from 'node:fs';

// 兼容 `--ts` 与 `ts` 两种写法：早期版本按不带前缀的 key 匹配，
// 传 `--ts` 会静默不匹配任何 job、照样打印「生成完成」——假绿灯，必须修。
const only = process.argv.slice(2).map((a) => a.replace(/^--/, ''));
const run = (cmd) => { console.log(`$ ${cmd}`); execSync(cmd, { stdio: 'inherit' }); };
const BUNDLE_DIR = 'generated/bundle';
const jobs = {
  ts: () => run('npx -y orval --config orval.config.ts'),
  // openapi-python-client 不支持外部 $ref（跨文件 ../schemas/*.yaml）：直接喂原契约会
  // 静默跳过引用了外部模型的端点（实测丢掉 GET /quota/summary 等）。先 bundle 成单文件。
  py: () => {
    mkdirSync(BUNDLE_DIR, { recursive: true });
    run(`npx -y @redocly/cli bundle ./openapi/console-api.yaml -o ${BUNDLE_DIR}/console-api.yaml`);
    // --overwrite：否则二次运行会撞「Directory already exists」直接失败。
    // 输出到 src/ 而非包根，避免连人写的 README.md 一起删掉。
    run(`uvx openapi-python-client generate --path ${BUNDLE_DIR}/console-api.yaml --output-path ../sdk-py/src --overwrite`);
  },
};

if (only.length === 0) { jobs.ts(); jobs.py(); }
else {
  for (const key of only) {
    const job = jobs[key];
    if (!job) {
      console.error(`未知的生成目标：${key}（可选：${Object.keys(jobs).join(' / ')}）`);
      process.exit(1);
    }
    job();
  }
}
console.log('生成完成：packages/sdk-ts（orval 输出）与 packages/sdk-py');
