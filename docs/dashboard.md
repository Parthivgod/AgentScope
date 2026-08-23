# AgentScope Dashboard Guide

Live execution-graph visualization and historical replay for AgentScope.

## Running

```powershell
cd dashboard
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/ingest`, `/traces`, `/history`, and `/ws` to the Nginx front door (`http://localhost:80` / `wss`-capable `:8443`), so the dashboard exercises the same path a deployed dashboard uses. The local stack (`infra/`) must be running.

## Using the dashboard

- **Live mode** (default): connects to `/ws`; every span streamed while the tab is open appears as a node, parent links become edges, and dagre lays the graph out top-to-bottom. Node states: ⟳ active (in-flight), ✓ complete, ✖ error, ⚠ anomalous (dashed amber border + AlertBadge). Click a node (or focus it with Tab and press Enter) to open the InspectPanel with inputs/outputs, timing, token usage, and anomaly details. Escape closes the panel.
- **Historical Replay**: the trace dropdown is populated from the real `GET /traces` endpoint (most recent first); selecting a trace fetches `/history/{id}` and renders it through the *same* graph component as live mode (RULES.md invariant #5 — one rendering path, only the event source differs). Failed fetches surface an explicit error banner; a cleared or missing trace never silently shows stale data.
- **Redaction indicator**: a 🔒 Redacted Data badge appears in the header whenever any visible span carries `[REDACTED]` payloads (SDK-side redaction was enabled).

## Accessibility

Verified with axe-core (0 violations) and Lighthouse (accessibility 100) — see CHANGELOG 2026-08-21 00:20 / 2026-08-22 01:40. Design rules to preserve when contributing:

- Node states must carry non-hue cues (status glyphs, dashed anomalous border) — never color alone; error-red vs. complete-green is indistinguishable under red-green color-vision deficiency.
- Every interactive element must be keyboard reachable (graph nodes are `role="button"` with `tabIndex=0`; Enter opens the InspectPanel).
- Text must meet ≥4.5:1 contrast on the dark theme (stat labels, node meta text).

## Repeatable checks

```powershell
node scripts/a11y-scan.mjs          # axe-core scan + Tab-order probe
node scripts/keyboard-nav-test.mjs  # Enter opens InspectPanel from keyboard
node scripts/escape-close-test.mjs  # Escape closes InspectPanel
npx lighthouse http://localhost:5173 --chrome-flags="--headless=new"  # scores
```

## Known notes

- The WebSocket only streams events from connection time onward — start the demo agent while the dashboard is open to see live traffic, or use Historical Replay for past traces.
- Lighthouse performance scores on the dev server are not representative of a production build.
