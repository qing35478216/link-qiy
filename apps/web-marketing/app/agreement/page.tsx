import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '使用协议',
  robots: { index: true },
};

/** 占位页：正式文案待法务评审后填入（内容走 CMS 时可迁移至 content/legal.json） */
export default function AgreementPage() {
  return (
    <section className="container-site max-w-3xl py-16">
      <h1 className="section-title">使用协议</h1>
      <p className="text-secondary mt-6 leading-relaxed">
        本页面为占位内容，正式《使用协议》文本待法务评审后发布。使用本平台即表示您同意遵守相关法律法规及平台规则。
      </p>
    </section>
  );
}
