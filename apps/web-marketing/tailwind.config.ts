import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 品牌主色（LinkAI 蓝），语义化命名，暗色模式走 CSS 变量覆盖
        brand: {
          DEFAULT: '#2E6BE6',
          50: '#EEF4FE',
          100: '#DCE8FD',
          500: '#2E6BE6',
          600: '#2559C4',
          700: '#1E48A0',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
      },
      keyframes: {
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        marquee: 'marquee 40s linear infinite',
        'fade-up': 'fade-up 0.5s ease-out both',
      },
    },
  },
  plugins: [],
};

export default config;
