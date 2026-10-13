import js from '@eslint/js';
import vue from 'eslint-plugin-vue';
import vueParser from 'vue-eslint-parser';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'public/mockServiceWorker.js'],
  },
  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
  },
  ...tseslint.configs.recommended,
  {
    rules: {
      // 防屎山军规 4：禁止 any / @ts-ignore / console.log
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/ban-ts-comment': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
      // 命名即文档
      camelcase: ['error', { properties: 'never' }],
      'vue/multi-word-component-names': 'error',
      'vue/no-v-html': 'error',
      'vue/require-default-prop': 'off',
      'vue/attributes-order': 'error',
    },
  },
  {
    files: ['**/*.test.ts', 'src/test-setup.ts', 'src/mocks/**'],
    rules: {
      'no-console': 'off',
    },
  },
  prettier,
);
