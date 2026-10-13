'use client';

import { useEffect, useState } from 'react';
import { home } from '@/lib/site';
import { Icon } from '../icons';

/** 场景解决方案轮播：自动播放 + 手动切换，响应式（移动端 1 列 / 桌面 3 列） */
export function ScenarioCarousel() {
  const { scenarios } = home;
  const [page, setPage] = useState(0);
  const perView = 3;
  const pageCount = Math.ceil(scenarios.items.length / perView);

  useEffect(() => {
    const t = setInterval(() => setPage((p) => (p + 1) % pageCount), 5000);
    return () => clearInterval(t);
  }, [pageCount]);

  const items = scenarios.items.slice(page * perView, page * perView + perView);

  return (
    <section id="scenarios" className="container-site py-16 sm:py-24">
      <div className="text-center">
        <h2 className="section-title">{scenarios.title}</h2>
        <p className="text-secondary mt-3">{scenarios.subtitle}</p>
      </div>
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <article key={item.title} className="card p-6 transition-shadow hover:shadow-lg">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-white/10 dark:text-brand-100">
              <Icon name={item.icon} className="h-6 w-6" />
            </span>
            <h3 className="mt-4 text-lg font-semibold">{item.title}</h3>
            <p className="text-secondary mt-2 text-sm leading-relaxed">{item.description}</p>
          </article>
        ))}
      </div>
      <div className="mt-8 flex justify-center gap-2">
        {Array.from({ length: pageCount }, (_, i) => (
          <button
            key={i}
            type="button"
            aria-label={`第 ${i + 1} 页`}
            onClick={() => setPage(i)}
            className={`h-2 rounded-full transition-all ${i === page ? 'w-6 bg-brand-500' : 'w-2 bg-brand-100 dark:bg-white/20'}`}
          />
        ))}
      </div>
    </section>
  );
}
