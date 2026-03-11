import { defineConfig } from 'tsup';

export default defineConfig([
  // Main SDK — ESM + CJS + types
  {
    entry: { index: 'src/index.ts' },
    format: ['esm', 'cjs'],
    dts: true,
    clean: true,
    sourcemap: true,
  },
  // Widget — self-contained IIFE for CDN / script tag
  {
    entry: { widget: 'src/widget.ts' },
    format: ['iife'],
    globalName: '_AAIWidget',
    outDir: 'dist',
    minify: true,
    sourcemap: false,
    // Bundle everything into one file — no imports needed at runtime
    bundle: true,
    platform: 'browser',
    target: 'es2020',
  },
]);
