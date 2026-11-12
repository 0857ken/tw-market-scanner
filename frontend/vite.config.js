import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  publicDir: process.env.VITE_RELEASE_PROFILE==='observation-only'?false:'public',
  plugins: [{
    name: 'local-dev-policy',
    apply: 'serve',
    // Local Vite HMR needs inline bootstrap and WebSockets; built output keeps CSP.
    transformIndexHtml: html => html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*\/>/, ''),
  },{
    name:'observation-only-policy',
    apply:'build',
    transformIndexHtml:html=>process.env.VITE_RELEASE_PROFILE==='observation-only'?html.replace("connect-src 'self' https://raw.githubusercontent.com;","connect-src 'self';"):html,
  }],
  build: {
    rollupOptions: {
      input: {
        scanner: fileURLToPath(new URL('./index.html', import.meta.url)),
        reboundMap: fileURLToPath(new URL('./rebound-map/index.html', import.meta.url)),
      },
      output: {
        manualChunks(id) {
          if (id.endsWith('/rebound-map/public-snapshot.json')) return 'rebound-public-data';
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react';
          if (/node_modules\/(recharts|recharts-scale|d3-[^/]+|lodash|victory-vendor|decimal\.js-light|react-smooth|react-transition-group|react-is|dom-helpers)\//.test(id)) return 'charts';
        }
      }
    }
  }
});
