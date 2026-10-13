import { home } from '@/lib/site';
import { CtaButton } from '../cta-button';

/**
 * 首页 Hero（对照 linkai-screenshots/23-agent-产品页.png 的版式：
 * 居中大标题 + 蓝色高亮 + 双 CTA + 底部四栏数据）。
 * 内容全部来自 content/home.json 的 hero 字段，改配置即改文案。
 */
export function HeroSection() {
  const { hero } = home;
  return (
    <section className="relative overflow-hidden">
      {/* 背景光晕：纯 CSS 渐变，无图片请求 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            'radial-gradient(60rem 30rem at 50% -10%, rgba(46,107,230,0.14), transparent 70%)',
        }}
      />
      <div className="container-site flex flex-col items-center py-20 text-center sm:py-28">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
          {hero.title}
          <span className="text-brand-500">{hero.titleHighlight}</span>
        </h1>
        <p className="text-secondary mt-6 max-w-3xl text-base leading-relaxed sm:text-lg">
          {hero.subtitle}
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
          {hero.ctas.map((cta) => (
            <CtaButton key={cta.label} cta={cta} />
          ))}
        </div>
      </div>
    </section>
  );
}
