import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./e2e', fullyParallel:false, workers:1, timeout:45000,
  reporter:[['list'],['json',{outputFile:'../test-results/e2e.json'}]],
  use:{baseURL:'http://127.0.0.1:4173/tw-market-scanner/',headless:true,screenshot:'only-on-failure',
    launchOptions:process.env.SCANNER_CHROMIUM_PATH?{executablePath:process.env.SCANNER_CHROMIUM_PATH,args:JSON.parse(process.env.SCANNER_CHROMIUM_ARGS||'[]')}:{}},
  projects:[{name:'chromium',use:{browserName:'chromium'}}],
  webServer:{command:'node ../scripts/serve-built.mjs',url:'http://127.0.0.1:4173/tw-market-scanner/',reuseExistingServer:!process.env.CI,timeout:20000}
});
