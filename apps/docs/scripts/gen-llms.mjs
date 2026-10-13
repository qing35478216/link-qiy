/**
 * 生成 llms.txt（https://llmstxt.org/ 约定）：站点导航 + 全部页面清单。
 * 在 vitepress build 后执行，产物 .vitepress/dist/llms.txt。
 */
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const dist = join(root, '.vitepress/dist');

if (!existsSync(dist)) {
  console.error('[gen-llms] 未找到构建产物 .vitepress/dist，请先 vitepress build');
  process.exit(1);
}

/** 从 HTML 提取 <title> 与 h1（无头轻量解析，避免引入依赖） */
function extract(html) {
  const title = html.match(/<title>([^<]+)<\/title>/)?.[1]?.trim() ?? '';
  const h1 = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/)?.[1]?.replace(/<[^>]+>/g, '')?.trim() ?? '';
  return { title, h1 };
}

const pages = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (name.endsWith('.html') && name !== '404.html') pages.push(p);
  }
})(dist);

const lines = [
  '# LinkAI 文档中心',
  '',
  '> LinkAI 一站式 AI 智能体平台官方文档：指南、嵌入 SDK、开放 API 与工程设计文档。',
  '',
  '## 文档',
  '',
];

for (const p of pages.sort()) {
  const rel = relative(dist, p).replace(/\\/g, '/').replace(/index\.html$/, '').replace(/\.html$/, '');
  const { title, h1 } = extract(readFileSync(p, 'utf8'));
  const label = h1 || title.replace(/\s*\|\s*LinkAI 文档中心$/, '') || rel;
  lines.push(`- [${label}](https://docs.link-ai.tech/${rel})`);
}

writeFileSync(join(dist, 'llms.txt'), lines.join('\n') + '\n');
console.log(`[gen-llms] 生成 llms.txt（${pages.length} 个页面）`);
