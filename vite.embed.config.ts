import { fileURLToPath, URL } from 'node:url';

import { defineConfig } from 'vite';

const path = (file: string) => fileURLToPath(new URL(file, import.meta.url));

// Builds embed/red-thread.ts as a self-contained ES module for pages without a bundler.
export default defineConfig({
  publicDir: false,
  build: {
    outDir: path('./dist-embed'),
    emptyOutDir: true,
    lib: {
      entry: path('./embed/red-thread.ts'),
      formats: ['es'],
      fileName: 'red-thread',
      cssFileName: 'red-thread',
    },
  },
});
