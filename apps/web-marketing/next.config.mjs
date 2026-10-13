/** @type {import('next').NextConfig} */
const nextConfig = {
  // 营销站是纯内容页：全量 SSG，产物为静态文件，可托管任意 CDN/对象存储。
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
