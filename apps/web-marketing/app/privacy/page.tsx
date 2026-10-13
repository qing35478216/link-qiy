import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '隐私政策',
  robots: { index: true },
};

/** 占位页：正式文案待法务评审后填入 */
export default function PrivacyPage() {
  return (
    <section className="container-site max-w-3xl py-16">
      <h1 className="section-title">隐私政策</h1>
      <p className="text-secondary mt-6 leading-relaxed">
        本页面为占位内容，正式《隐私政策》文本待法务评审后发布。我们重视您的数据安全，遵循最小化收集原则。
      </p>
    </section>
  );
}
