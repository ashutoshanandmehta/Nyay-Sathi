import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir:'./e2e', timeout:30_000, retries:0, reporter:'line', use:{baseURL:'http://127.0.0.1:5174',trace:'retain-on-failure'},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['Pixel 7']}}],
  webServer:[
    {command:'cd ../backend && ASSISTANT_ENGINE=legacy OPENAI_API_KEY= REQUESTS_PER_MINUTE=600 DATABASE_PATH=../runtime/playwright/nyay.sqlite3 CHECKPOINT_PATH=../runtime/playwright/checkpoints.sqlite3 CHROMA_PATH=../runtime/playwright/chroma UPLOAD_PATH=../runtime/playwright/uploads EXPORT_PATH=../runtime/playwright/exports .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100',url:'http://127.0.0.1:8100/api/health',reuseExistingServer:false,timeout:60_000},
    {command:'npm run dev -- --config vite.e2e.config.ts --host 127.0.0.1 --port 5174',url:'http://127.0.0.1:5174',reuseExistingServer:false,timeout:60_000}
  ]
})
