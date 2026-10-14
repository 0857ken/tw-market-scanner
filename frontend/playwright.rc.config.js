import {defineConfig} from '@playwright/test';
import base from './playwright.config.js';
export default defineConfig({...base,testIgnore:[],testMatch:'observation-rc.spec.js',
  reporter:[['list'],['json',{outputFile:'../test-results/stage4a-e2e.json'}]],
  webServer:{...base.webServer,command:'SCANNER_RC=true node ../scripts/serve-built.mjs',reuseExistingServer:false}
});
