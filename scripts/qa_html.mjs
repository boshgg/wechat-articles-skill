import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const outputFlag = args.indexOf('--out');
if (outputFlag < 0 || !args[outputFlag + 1]) {
  throw new Error('Usage: node scripts/qa_html.mjs --out QA_DIRECTORY ARTICLE.html [ARTICLE.html ...]');
}
const out = path.resolve(args[outputFlag + 1]);
args.splice(outputFlag, 2);
if (!args.length || args.some(arg => arg.startsWith('--'))) throw new Error('Specify HTML files explicitly.');
let moduleName = process.env.PLAYWRIGHT_MODULE || 'playwright';
if (path.isAbsolute(moduleName)) moduleName = pathToFileURL(moduleName).href;
const { chromium } = await import(moduleName);
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true });
const results = [];
try {
  for (let articleIndex = 0; articleIndex < args.length; articleIndex++) {
    const file = path.resolve(args[articleIndex]);
    for (const viewport of [{ name: 'mobile', width: 390, height: 844 }, { name: 'desktop', width: 1440, height: 900 }]) {
      const page = await browser.newPage({ viewport });
      await page.goto(pathToFileURL(file).href, { waitUntil: 'load', timeout: 30000 });
      await page.evaluate(() => document.fonts.ready);
      const metrics = await page.evaluate(() => {
        const width = document.documentElement.clientWidth;
        const elements = [...document.querySelectorAll('main *')];
        const overflows = elements.filter(el => {
          const r = el.getBoundingClientRect();
          return r.width && (r.left < -1 || r.right > width + 1 || (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1));
        }).map(el => ({ tag: el.tagName, text: el.textContent.slice(0, 100) }));
        const hiddenText = elements.filter(el => {
          const hasText = [...el.childNodes].some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
          if (!hasText) return false;
          const style = getComputedStyle(el);
          return style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0 || Number.parseFloat(style.fontSize) === 0;
        }).map(el => el.textContent.slice(0, 100));
        const brokenImages = [...document.images].filter(img => !img.complete || !img.naturalWidth).length;
        const distortedImages = [...document.images].filter(img => {
          const r = img.getBoundingClientRect();
          return img.naturalWidth && (!r.height || Math.abs(r.width / r.height - img.naturalWidth / img.naturalHeight) > 0.02);
        }).length;
        return { width, scrollWidth: document.documentElement.scrollWidth,
          layout: document.querySelector('main')?.dataset.layout,
          images: document.images.length, brokenImages, distortedImages,
          tables: document.querySelectorAll('main table').length, overflows, hiddenText };
      });
      const prefix = `${articleIndex + 1}-${viewport.name}`;
      await page.screenshot({ path: path.join(out, `${prefix}-top.png`) });
      await page.screenshot({ path: path.join(out, `${prefix}-full.png`), fullPage: true });
      if (viewport.name === 'mobile') {
        const details = page.locator('section[data-role="table"],section[data-role="cover"],section[data-role="illustration"]');
        for (let i = 0; i < await details.count(); i++) {
          await details.nth(i).screenshot({ path: path.join(out, `${prefix}-detail-${i + 1}.png`) });
        }
      }
      results.push({ file, html_sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),
        viewport: viewport.name, screenshots: prefix, ...metrics,
        manual_screenshot_review: 'not_run', wechat_paste: 'not_run' });
      await page.close();
    }
  }
} finally {
  await browser.close();
}
fs.writeFileSync(path.join(out, 'browser-checks.json'), JSON.stringify(results, null, 2));
console.log(JSON.stringify(results, null, 2));
if (results.some(r => r.overflows.length || r.hiddenText.length || r.brokenImages || r.distortedImages || r.scrollWidth > r.width || r.layout !== 'jinpeng-reference-v2')) process.exitCode = 1;
