import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import tseslintParser from '@typescript-eslint/parser';
import tseslintPlugin from '@typescript-eslint/eslint-plugin';
import eslintConfigPrettier from 'eslint-config-prettier';
import globals from 'globals';

/**
 * packages/ui ESLint flat 配置（strict）。
 * 组件库消费方众多：禁 any / 禁 console.log / 组件名多词 / 禁 v-html。
 */
export default [
  {
    ignores: ['dist/**', 'node_modules/**'],
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
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
      'no-var': 'error',
      'prefer-const': 'error',
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslintParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
      globals: { ...globals.browser },
    },
    rules: {
      'vue/multi-word-component-names': 'error',
      'vue/no-v-html': 'error',
      'vue/attribute-hyphenation': 'error',
      'vue/require-default-prop': 'error',
      'vue/v-on-event-hyphenation': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
    },
  },
  eslintConfigPrettier,
];
