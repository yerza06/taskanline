import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // Генерируемые файлы: schema.d.ts собирает openapi-typescript, routeTree.gen.ts —
  // плагин роутера. Править их руками нельзя, а значит и замечания линтера по ним
  // некому исполнять.
  {
    ignores: [
      'dist',
      'coverage',
      'node_modules',
      'src/shared/api/schema.d.ts',
      'src/routeTree.gen.ts',
    ],
  },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    // Маршрут — это модуль с экспортом `Route` и локальным компонентом рядом:
    // такова форма файловой маршрутизации, и разносить их по файлам незачем.
    // `throw redirect(...)` — её же идиома: роутер ловит объект перехода, а не ошибку.
    files: ['src/routes/**/*.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
      '@typescript-eslint/only-throw-error': 'off',
    },
  },
  {
    files: ['**/*.test.{ts,tsx}', 'src/test/**'],
    rules: { '@typescript-eslint/no-unsafe-assignment': 'off' },
  },
)
