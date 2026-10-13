import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import tseslintParser from '@typescript-eslint/parser';
import tseslintPlugin from '@typescript-eslint/eslint-plugin';
import vueParser from 'vue-eslint-parser';
import eslintConfigPrettier from 'eslint-config-prettier';
import globals from 'globals';

/**
 * apps/web-console ESLint flat 配置（strict）。
 * 防屎山军规 4：禁 any / 禁 @ts-ignore / 禁 console.log；命名即文档。
 */
export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'public/mockServiceWorker.js'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tseslintParser,
      parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
      globals: { ...globals.browser },
    },
    plugins: { '@typescript-eslint': tseslintPlugin },
    rules: {
      ...tseslintPlugin.configs['recommended'].rules,
      // TS 已覆盖未定义变量检查；base 规则不理解类型位置（defineEmits 泛型等）
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/ban-ts-comment': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
      'no-var': 'error',
      'prefer-const': 'error',
      camelcase: ['error', { properties: 'never' }],
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslintParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
      globals: { ...globals.browser },
    },
    plugins: { '@typescript-eslint': tseslintPlugin },
    rules: {
      'vue/multi-word-component-names': 'error',
      'vue/no-v-html': 'error',
      'vue/attribute-hyphenation': 'error',
      'vue/v-on-event-hyphenation': 'error',
      'vue/require-default-prop': 'off',
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
    },
  },
  {
    files: ['src/test-setup.ts', 'src/mocks/**', 'src/tests/**', '*.config.ts'],
    rules: {
      'no-console': 'off',
    },
  },
  eslintConfigPrettier,
];
