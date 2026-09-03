# Usability Study Readiness Check — 2026-09-03

Tested the current working tree against the local production Compose stack, a Vite development dashboard, and seeded LangGraph demo traces.

## Automated observations

- Dashboard production build: pass.
- Dashboard oxlint: pass.
- Demo-readiness browser check: pass.
- Historical replay: 4 nodes and 3 edges.
- Live injected failure: 3 nodes, 3 anomalous nodes, 9 alert-related elements.
- Browser console/page errors: 0.
- axe-core: 0 violations and 34 passes. It also returned 14 incomplete checks requiring human review: 2 `aria-prohibited-attr` nodes and 12 `color-contrast` nodes.
- Keyboard probe reached Live, Historical Replay, summary/legend controls, zoom controls, and the document body in the empty initial live view.

## Interpretation

The scripted scenario is technically ready for a participant session, subject to manual review of the 14 incomplete axe checks and the consent/ethics gate. This is not usability evidence: no unfamiliar participant completed a task, so task success, diagnosis time, SUS, and qualitative findings remain unmeasured.
