import { defineConfig } from 'tsup'

export default defineConfig({
  entry: ['src/cli.tsx'],
  format: ['esm'],
  target: 'node18',
  bundle: true,
  outExtension: () => ({ js: '.js' }),
  minify: false,
  sourcemap: true,
  clean: true,
  banner: () => `#!/usr/bin/env node`,
})
