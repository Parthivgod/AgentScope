/** Week 12 demo-readiness: no console errors, live demo renders nodes+edges, anomaly alert appears. */
import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage();
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));

await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);

// 1. Replay mode works on seeded traces
await page.getByRole('button', { name: 'Historical Replay' }).click();
await page.waitForTimeout(800);
await page.locator('select').selectOption('trace-linear-demo-1');
await page.waitForTimeout(1200);
const repNodes = await page.locator('.react-flow__node').count();
const repEdges = await page.locator('.react-flow__edge').count();

// 2. Live mode + anomaly injection
await page.getByRole('button', { name: 'Live' }).click();
await page.waitForTimeout(800);
const inj = await page.evaluate(async () => {
  const span = (i) => ({
    trace_id: 'demo-anomaly', span_id: crypto.randomUUID(), parent_span_id: null,
    span_type: 'tool_call', name: 'flaky_tool', input: { attempt: i }, output: null,
    start_time: new Date().toISOString(), end_time: new Date().toISOString(),
    status: { status: 'error', exception_details: 'tool timeout' }, token_usage: null,
    agent_id: 'demo-agent',
  });
  for (let i = 0; i < 3; i++) {
    await fetch('/ingest', { method: 'POST', headers: { Authorization: 'Bearer test-key', 'Content-Type': 'application/json' }, body: JSON.stringify(span(i)) });
  }
  return 'ok';
});
await page.waitForTimeout(3500);
const liveNodes = await page.locator('.react-flow__node').count();
const anomalous = await page.locator('.agent-node--anomalous').count();
const alertBadge = await page.locator('.alert-badge, [class*="alert"]').count();

console.log(`replay: ${repNodes} nodes / ${repEdges} edges`);
console.log(`live after injection(${inj}): ${liveNodes} nodes, anomalous nodes: ${anomalous}, alert elements: ${alertBadge}`);
console.log(`console errors: ${errors.length}${errors.length ? ' -> ' + errors.slice(0,3).join(' | ') : ' (none)'}`);
const ok = repNodes > 0 && repEdges > 0 && liveNodes > 0 && anomalous > 0 && errors.length === 0;
console.log(`DEMO-READY: ${ok ? 'PASS' : 'FAIL'}`);
await browser.close();
process.exit(ok ? 0 : 1);
