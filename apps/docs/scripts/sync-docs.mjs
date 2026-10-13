/**
 * 将仓库根 docs/ 同步到文档站 design/ 目录（补 frontmatter，映射文件名）。
 * 用法：pnpm sync（构建前执行）。构建命令已串联：docs:build = vitepress build && gen-llms。
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = join(here, '../../../docs');
const outDir = join(here, '../design');

/** 仓库 docs/ 文件名 → [文档站路径, 标题]（与 sidebar 一致） */
const MAP = {
  '01-功能拆解蓝图.md': ['01-blueprint.md', '功能拆解蓝图'],
  '02-团队组建与开发实施方案.md': ['02-team-plan.md', '团队组建与开发实施方案'],
  '03-开发实现框架设计.md': ['03-architecture.md', '开发实现框架设计'],
  '04-模块级实施规格.md': ['04-module-spec.md', '模块级实施规格'],
  '05-AI开发团队与提示词工程.md': ['05-ai-team.md', 'AI 开发团队与提示词工程'],
  'observability.md': ['observability.md', '可观测性'],
};

if (!existsSync(srcDir)) {
  console.error(`[sync-docs] 未找到仓库 docs/：${srcDir}`);
  process.exit(1);
}
mkdirSync(outDir, { recursive: true });

let copied = 0;
for (const file of readdirSync(srcDir)) {
  const entry = MAP[file];
  if (!entry) continue;
  const [target, title] = entry;
  const body = readFileSync(join(srcDir, file), 'utf8');
  const frontmatter = `---\ntitle: ${title}\neditLink: false\n---\n\n`;
  writeFileSync(join(outDir, target), frontmatter + body);
  copied += 1;
}
console.log(`[sync-docs] 同步 ${copied} 个文件到 design/`);
