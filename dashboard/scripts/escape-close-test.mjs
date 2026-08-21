/** Week 10: Escape closes the InspectPanel. */
import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage();
await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);
await page.getByRole('button', { name: 'Historical Replay' }).click();
await page.waitForTimeout(1200);
await page.locator('.agent-node').first().focus();
await page.keyboard.press('Enter');
await page.waitForTimeout(500);
const open = await page.getByRole('button', { name: 'Close panel' }).count();
await page.keyboard.press('Escape');
await page.waitForTimeout(500);
const closed = await page.getByRole('button', { name: 'Close panel' }).count();
console.log(`panel open after Enter: ${open === 1}; closed after Escape: ${closed === 0}`);
await browser.close();
process.exit(open === 1 && closed === 0 ? 0 : 1);
