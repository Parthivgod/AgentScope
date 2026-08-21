/**
 * Week 9 accessibility scan (Track C): axe-core against the live local dashboard,
 * plus keyboard-navigation probing. Drives the system Chrome via playwright-core
 * (no browser download needed).
 *
 * Usage: node scripts/a11y-scan.mjs [url]
 */
import { chromium } from 'playwright-core';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { source: axeSource } = require('axe-core');

const url = process.argv[2] || 'http://localhost:5173/';
const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const browser = await chromium.launch({ executablePath: chrome, headless: true });
const page = await browser.newPage();
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);

// --- axe-core scan ---
await page.evaluate(axeSource);
const results = await page.evaluate(async () => {
  const r = await window.axe.run(document, {
    resultTypes: ['violations', 'passes', 'incomplete'],
  });
  return {
    violations: r.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
      targets: v.nodes.slice(0, 3).map((n) => n.target.join(' ')),
    })),
    passes: r.passes.length,
    incomplete: r.incomplete.map((v) => ({ id: v.id, help: v.help, nodes: v.nodes.length })),
  };
});

console.log(JSON.stringify(results, null, 2));

// --- keyboard navigation probe: what does Tab reach, and in what order? ---
const tabStops = [];
for (let i = 0; i < 15; i++) {
  await page.keyboard.press('Tab');
  const info = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return '(body)';
    const label = el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 40) || el.tagName;
    return `${el.tagName.toLowerCase()}: "${label}"`;
  });
  tabStops.push(info);
}
console.log('\nTAB ORDER:', JSON.stringify(tabStops, null, 2));

await browser.close();
