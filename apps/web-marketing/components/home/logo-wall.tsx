import { home } from '@/lib/site';

/** 客户 Logo 墙：纯 CSS 跑马灯（文本 Logo，无外链图片依赖，暗色/亮色自适应） */
export function LogoWall() {
  const { logoWall } = home;
  const row = [...logoWall.logos, ...logoWall.logos];
  return (
    <section id="logos" className="border-y py-12" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
      <div className="container-site">
        <h2 className="section-title text-center text-xl sm:text-2xl">{logoWall.title}</h2>
      </div>
      <div className="relative mt-8 overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24" style={{ background: 'linear-gradient(to right, var(--bg-soft), transparent)' }} />
        <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24" style={{ background: 'linear-gradient(to left, var(--bg-soft), transparent)' }} />
        <div className="marquee-track flex w-max animate-marquee gap-4">
          {row.map((logo, i) => (
            <div key={`${logo.name}-${i}`} className="card flex h-14 w-36 items-center justify-center gap-2 px-4" aria-hidden={i >= logoWall.logos.length}>
              <span className="text-secondary inline-flex h-7 w-7 items-center justify-center rounded-md bg-brand-50 text-xs font-bold text-brand-600 dark:bg-white/10 dark:text-brand-100">
                {logo.text.slice(0, 1)}
              </span>
              <span className="text-secondary text-sm font-medium">{logo.text}</span>
            </div>
          ))}
        </div>
      </div>
      <p className="text-secondary mt-6 text-center text-xs">{logoWall.note}</p>
    </section>
  );
}
