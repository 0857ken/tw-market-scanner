import {defineConfig} from '@playwright/test';
import base from './playwright.config.js';
export default defineConfig({...base,testIgnore:[],testMatch:'daily-release.spec.js',reporter:[['list'],['json',{outputFile:'../test-results/stage4c1-browser.json'}]],webServer:{...base.webServer,command:'SCANNER_DAILY=true node ../scripts/serve-built.mjs',reuseExistingServer:false}});
