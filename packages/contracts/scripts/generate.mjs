#!/usr/bin/env node
/**
 * SDK 生成入口（铁律 8：选型对比见 ADOPTED-TOOLS.md）
 *   sdk-ts: orval（axios 客户端 + 类型 + MSW handlers）
 *   sdk-py: openapi-python-client（httpx + pydantic v2）
 *
 * 用法：npm run generate [-- --ts|--py]（缺省全量）
 * 前置：packages/contracts 已 pnpm/npm install（orval/redocly 在 devDeps）；
 *       openapi-python-client 经 uvx 调用（uv 工具链）。
 *
 * 环境注意：不要用 `npx -y <bin>`——沙箱/代理环境下 -y 会触发联网检查，
 * 导致 bin 启动失败（command not found）。这里直接解析 node_modules/.bin 绝对路径。
 */
import { execSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const bin = (name) => join(here, '..', 'node_modules', '.bin', name);
const sdkPyPkg = join(here, '..', '..', 'sdk-py', 'src', 'link_ai_console');

// 兼容 `--ts` 与 `ts` 两种写法：早期版本按不带前缀的 key 匹配，
// 传 `--ts` 会静默不匹配任何 job、照样打印「生成完成」——假绿灯，必须修。
const only = process.argv.slice(2).map((a) => a.replace(/^--/, ''));
const run = (cmd) => { console.log(`$ ${cmd}`); execSync(cmd, { stdio: 'inherit' }); };
const BUNDLE_DIR = 'generated/bundle';
const jobs = {
  ts: () => run(`${bin('orval')} --config orval.config.ts`),
  // openapi-python-client 不支持外部 $ref（跨文件 ../schemas/*.yaml）：直接喂原契约会
  // 静默跳过引用了外部模型的端点（实测丢掉 GET /quota/summary 等）。先 bundle 成单文件。
  py: () => {
    mkdirSync(BUNDLE_DIR, { recursive: true });
    run(`${bin('redocly')} bundle ./openapi/console-api.yaml -o ${BUNDLE_DIR}/console-api.yaml`);
    // --overwrite 只覆盖文件，对已存在的包目录仍会 mkdir EEXIST（沙箱下直接抛
    // PermissionError）——先删掉旧包目录再生成（纯生成物，git 可恢复）。
    rmSync(sdkPyPkg, { recursive: true, force: true });
    // --config：覆盖默认包名（info.title 含中文，Python 标识符必须 ASCII 安全）。
    run(`uvx openapi-python-client generate --path ${BUNDLE_DIR}/console-api.yaml --output-path ../sdk-py/src --overwrite --config ./scripts/openapi-python-client.config.yaml`);
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
