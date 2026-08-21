/** Week 9 keyboard-navigation verification: tab to a graph node, press Enter, InspectPanel must open. */
import { chromium } from 'playwright-core';

const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage();
await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);

// Historical replay so nodes exist without needing live traffic
await page.getByRole('button', { name: 'Historical Replay' }).click();
await page.waitForTimeout(1200);

const nodeCount = await page.locator('.agent-node').count();
console.log('nodes on screen:', nodeCount);

// Focus the first node via keyboard and press Enter
await page.locator('.agent-node').first().focus();
const focused = await page.evaluate(() => {
  const el = document.activeElement;
  return el ? el.getAttribute('aria-label') : null;
});
console.log('focused node aria-label:', focused);

await page.keyboard.press('Enter');
await page.waitForTimeout(600);

// InspectPanel visibility
const panelVisible = await page.getByRole('button', { name: 'Close panel' }).count();
console.log('InspectPanel close button present after Enter:', panelVisible === 1 ? 'YES' : 'NO');

await browser.close();
