import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react';
          if (/node_modules\/(recharts|recharts-scale|d3-[^/]+|lodash|victory-vendor|decimal\.js-light|react-smooth|react-transition-group|react-is|dom-helpers)\//.test(id)) return 'charts';
        }
      }
    }
  }
});
