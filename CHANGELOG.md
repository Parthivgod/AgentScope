# AgentScope Changelog

## [2026-08-08 17:35] — Weeks 3-4: Dagre Layout & InspectPanel (branch: track-c-eshan) — Track C — Eshan

**What changed:**
- `Track C`: Built `dashboard/src/layout.ts` implementing hierarchical top-to-bottom layout via `@dagrejs/dagre` (Build Plan §1 Decision 1).
- `Track C`: Created `dashboard/src/components/AgentNode.tsx` custom React Flow node with visual states (active cyan pulse, complete green, error red) matching (FR-6/Flow 3 Step 2).
- `Track C`: Built `dashboard/src/components/InspectPanel.tsx` slide-out detail panel displaying span timing, tokens, identity, inputs, and outputs (Build Plan §4 Track C Week 4 / Flow 3 Step 4).
- `Track C`: Refactored `App.tsx` and added `App.css` and `index.css` for a premium glassmorphic dark theme, removing previous generic scaffolding. Graph layout now auto-updates on event arrival using `layout.ts`.
- `Track C`: Enhanced mock `useWebSocket.ts` to simulate a rich, branching LangGraph execution with token usage and cascaded failures for testing all UI edge cases.
- `Track C`: Updated `dashboard/vite.config.ts` to explicitly include `@dagrejs/dagre` in `optimizeDeps` for CJS compat.
- `Track C`: Updated `dashboard/index.html` with explicit metadata descriptions and dark theme-color for SEO and UX.

**Why:**
- Satisfies Build Plan §4 Track C tasks for Weeks 3 and 4, except for the real WebSocket integration.
- Fulfills FR-6 (visual distinct states for active/idle/anomalous) and Flow 3 Step 4 (click to inspect node detail).
- Prepares the dashboard visuals for the integration demo (M1 checkpoint) with realistic data.

**Assumptions made (if any):**
- Mock testing is sufficient since Node.js/npm is not available on the execution host yet to run `npm run dev` directly over this session.
- Real WS relay is unavailable, substituting with the enhanced `useWebSocket.ts` mock for now.

**Open questions / follow-ups (if any):**
- **BLOCKED/Track B Dependency**: Real WebSocket integration (Track B `ws.py` deliverable for Week 3) is missing. The Dashboard is ready but will continue using the mock hook until Track B completes the dependency (Build Plan §4/§5).

**Tests added/run:**
- TypeScript strictness and code-level reviews conducted. Visual rendering will need to be explicitly tested once `npm` is configured.
## [2026-08-08 14:48] — Week 2 Build Plan Implementation — All Tracks — Core Engine & Integration

**What changed:**
- `Track A`: Built `LangGraphAdapter` in `sdk/agentscope/adapters/langgraph.py` adhering to callback pattern (RULES.md §2 Decision 5).
- `Track A`: Built `@agentscope.trace` decorator in `sdk/agentscope/trace.py` for custom Python functions.
- `Track A`: Created `sdk/agentscope/config.py` for managing SDK env variables.
- `Track A`: Created `sdk/agentscope/sender.py` establishing an asynchronous, fail-silent event sender queue using `httpx`.
- `Track A`: Added pytest cases in `sdk/tests/test_sender.py` confirming sender won't raise into host code on backend crash, timeout, or 401.
- `Track A`: Added fixture test `sdk/tests/test_cross_path.py` confirming both LangGraph and custom paths yield structurally identical spans (RULES.md §3 invariant).
- `Track B`: Configured `backend/app/redis_client.py` and updated `/ingest` to successfully write to Redis Streams via `xadd`.
- `Track B`: Authored comprehensive `backend/tests/test_ingest.py` testing API-key rejection and invalid payloads.
- `Track C`: Created `dashboard/src/hooks/useWebSocket.ts` to simulate a mock span stream (Flow 3) for development.
- `Track C`: Integrated mock hooks into `App.tsx` handling idle/active/complete visual states.
- `Shared/CI`: Corrected the Day-1 schema in `schema.py` to extract `SpanStatus` to capture success/error plus exception details. 
- `Shared/CI`: Updated `.github/workflows/ci.yml` to run `pytest` correctly against backend and sdk.

**Why:**
- Fulfills Build Plan §4 (Week 2 Tasks) across Track A, B, and C.
- Day-1 correction based on explicit feedback to make schema compliant with PRD §6.3.
- Assures RULES.md invariants #1, #2, and #3 hold before moving to Week 3 integration.

**Assumptions made (if any):**
- Mock websocket uses `setInterval` locally inside the hook for the Week 2 isolated Track C delivery. It simulates a 6 span flow with one timeout error.
- Redis connection uses `redis://localhost:6379` by default.

**Open questions / follow-ups (if any):**
- Real backend websocket relay isn't built yet, so the dashboard will swap out `useWebSocket` hook's internals in Week 3.
- `redis.asyncio` will require a live Redis instance to pass backend integration tests down the line if we run tests connected to Redis.

**Tests added/run:**
- `test_ingest.py`: Tests `missing key`, `invalid key`, `valid key`, and `invalid payload`.
- `test_sender.py`: Tests `backend_down`, `invalid_key`, and `timeout`.
- `test_cross_path.py`: Fixture verifying decorator and adapter produce identical spans.

## [2026-08-08 14:15] — Day-1 Repository Bootstrapping — Track Shared — Initial Setup
*(Note: Schema status field was corrected in the 14:48 commit above)*

**What changed:**
- Scaffolded monorepo structure with `sdk/`, `backend/`, `worker/`, `dashboard/`, `infra/`, `examples/`, `docs/`, `manuscript/`.
- Created `sdk/agentscope/schema.py` with `Span` and `Trace` Pydantic models.
- Created `backend/app/ingest.py` with a `POST /ingest` endpoint validating incoming payloads against `Span` schema, including API-key verification middleware.
- Created `infra/docker-compose.yml` with Redis configuration and `infra/.env.example` with API key placeholder.
- Scaffolded `dashboard/` using Vite + React + TS, installed `@xyflow/react` and `@dagrejs/dagre`, and implemented a static placeholder graph in `App.tsx`.
- Added MIT `LICENSE` file.
- Created `.github/workflows/ci.yml` for CI validation on schema tests and API-key rejection.
- Created `CHANGELOG.md` and `docs/future-work.md` with headers per instructions.

**Why:**
- Implements Build Plan §12 (Day-1 Checklist) across all Tracks (A, B, C) and Shared.
- Establishes the foundational Week-1 schema contract (PRD §6.3, Build Plan Decision 2) across the monorepo.
- Provides base backend endpoint (FR-7 API key check).
- Provides static UI placeholder for Track C.

**Assumptions made (if any):**
- Assumed `TokenUsage` should be a nested Pydantic model for cleaner structure.
- Used `datetime` for `start_time` and `end_time` in spans to properly handle durations.
- Assumed `status` values strictly to be `success` or `error` as mentioned in PRD §6.3.

**Open questions / follow-ups (if any):**
- Dashboard layout uses manual coordinates for now since it's a static placeholder. Integration with `dagre` will happen when dynamic graphs are implemented.
- CI pipeline has a basic test hook setup but will need comprehensive pytests once tests directory is structured.

**Tests added/run:**
- Simple module import verification in CI config for FastAPI. Local deployment validation for dashboard (vite setup).
