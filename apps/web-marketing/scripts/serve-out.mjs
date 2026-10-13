#!/usr/bin/env node
/**
 * 静态预览服务器：服务 `next build` 导出的 out/ 目录。
 *
 * 用途：本地产物验证（Lighthouse / 响应式 / 暗色模式截图）。
 * 行为对齐真实 CDN 托管——目录 index、扩展名补全、404 回落、gzip 压缩。
 *
 * 压缩不是"为跑分而美化"：生产环境 nginx / Cloudflare / Vercel 默认开启压缩，
 * 不开压缩的本地服务器会让 Lighthouse 测出失真的传输体积与 FCP。
 * 压缩结果在启动时预生成并缓存（对齐 CDN 直接下发预压缩产物），
 * 而非每个请求实时压缩——实时 brotli 的 CPU 开销会反过来拖慢 FCP，让测量失真。
 *
 * 用法：node scripts/serve-out.mjs [port]   默认 8899
 */
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync, readdirSync } from 'node:fs';
import { extname, join, normalize, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'out');
const port = Number(process.argv[2] ?? 8899);

if (!existsSync(root)) {
  console.error(`未找到导出目录：${root}\n请先执行 pnpm --filter @linkai/web-marketing build`);
  process.exit(1);
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
};

/** 已压缩的二进制（jpg/png/ico 本身即压缩格式，再压收益为负） */
const INCOMPRESSIBLE = new Set(['image/png', 'image/jpeg', 'image/x-icon', 'font/woff2']);

/** 启动时遍历产物，预生成 gzip 缓存：Map<磁盘路径, {raw, gz}> */
const cache = new Map();
(function precompress(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) precompress(p);
    else {
      const raw = readFileSync(p);
      const type = MIME[extname(p)] ?? 'application/octet-stream';
      cache.set(p, INCOMPRESSIBLE.has(type) ? { raw, gz: null } : { raw, gz: gzipSync(raw, { level: 9 }) });
    }
  }
})(root);

/** 把 URL 路径解析为磁盘文件；找不到则回落到 404.html */
function resolve(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split('?')[0])).replace(/^(\.\.[/\\])+/, '');
  const candidates = clean.endsWith('/')
    ? [join(root, clean, 'index.html')]
    : [join(root, clean), join(root, `${clean}.html`), join(root, clean, 'index.html')];

  for (const p of candidates) {
    if (p.startsWith(root) && cache.has(p)) return p;
  }
  return null;
}

createServer((req, res) => {
  const file = resolve(req.url ?? '/');
  const notFound = join(root, '404.html');

  if (!file) {
    const body = cache.get(notFound) ?? { raw: readFileSync(notFound), gz: null };
    res.writeHead(404, { 'content-type': MIME['.html'] });
    res.end(req.headers['accept-encoding']?.includes('gzip') && body.gz ? body.gz : body.raw);
    return;
  }

  const entry = cache.get(file);
  const type = MIME[extname(file)] ?? 'application/octet-stream';
  const wantsGzip = /\bgzip\b/.test(req.headers['accept-encoding'] ?? '') && entry.gz;
  const headers = { 'content-type': type, 'cache-control': 'no-store' };
  if (wantsGzip) headers['content-encoding'] = 'gzip';

  res.writeHead(200, headers);
  res.end(wantsGzip ? entry.gz : entry.raw);
}).listen(port, '127.0.0.1', () => {
  const total = [...cache.values()].reduce((n, e) => n + e.raw.length, 0);
  const gz = [...cache.values()].reduce((n, e) => n + (e.gz ? e.gz.length : e.raw.length), 0);
  console.log(
    `预览服务已启动：http://127.0.0.1:${port}  (root=${root})\n` +
      `已缓存 ${cache.size} 个文件，gzip 后 ${(gz / 1024).toFixed(0)}KiB / 原始 ${(total / 1024).toFixed(0)}KiB`,
  );
});
