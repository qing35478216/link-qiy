#!/usr/bin/env node
/**
 * 静态预览服务器：服务 `next build` 导出的 out/ 目录。
 *
 * 用途：本地产物验证（Lighthouse / 响应式 / 暗色模式截图）。
 * 行为对齐 CDN 上的真实托管——目录 index、扩展名补全、404 回落。
 *
 * 用法：node scripts/serve-out.mjs [port]   默认 8899
 */
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

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

/** 把 URL 路径解析为磁盘文件；找不到则回落到 404.html */
function resolve(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split('?')[0])).replace(/^(\.\.[/\\])+/, '');
  const candidates = clean.endsWith('/')
    ? [join(root, clean, 'index.html')]
    : [join(root, clean), join(root, `${clean}.html`), join(root, clean, 'index.html')];

  for (const p of candidates) {
    if (p.startsWith(root) && existsSync(p) && statSync(p).isFile()) return p;
  }
  return null;
}

createServer((req, res) => {
  const file = resolve(req.url ?? '/');
  if (!file) {
    const notFound = join(root, '404.html');
    res.writeHead(404, { 'content-type': MIME['.html'] });
    createReadStream(existsSync(notFound) ? notFound : __filename).pipe(res);
    return;
  }
  res.writeHead(200, {
    'content-type': MIME[extname(file)] ?? 'application/octet-stream',
    'cache-control': 'no-store',
  });
  createReadStream(file).pipe(res);
}).listen(port, '127.0.0.1', () => {
  console.log(`预览服务已启动：http://127.0.0.1:${port}  (root=${root})`);
});
