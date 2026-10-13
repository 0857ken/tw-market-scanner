import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  plugins: [{
    name: 'local-dev-policy',
    apply: 'serve',
    // Local Vite HMR needs inline bootstrap and WebSockets; built output keeps CSP.
    transformIndexHtml: html => html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*\/>/, ''),
  }],
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
