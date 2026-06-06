import { defineConfig } from 'tsup'

export default defineConfig({
  entry: { 'mmi-tui': 'src/cli.tsx' },
  format: ['esm'],
  target: 'node18',
  bundle: true,
  outExtension: () => ({ js: '.js' }),
  minify: false,
  sourcemap: true,
  clean: true,
  banner: {},
})
