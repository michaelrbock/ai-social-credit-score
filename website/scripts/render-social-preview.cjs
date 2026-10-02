#!/usr/bin/env node
// Optional authoring utility. The website serves the checked-in PNG without a build.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1,
    });
    await page.goto(pathToFileURL(path.resolve(__dirname, '../design/social-preview.html')).href);
    await page.evaluate(async () => {
      await document.fonts.ready;
      if (!document.fonts.check('500 78px "DM Sans"')) throw new Error('DM Sans did not load');
    });
    const output = path.resolve(__dirname, '../dist/social-preview.png');
    await page.screenshot({ path: output, type: 'png', animations: 'disabled' });
    console.log(`Rendered 1200 × 630 social preview: ${output}`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
