# AgentScope Changelog

## [2026-08-10 14:45] — Track A Weeks 3 & 4 Implementation — Track A — Nilay Jain

**What changed:**
- `Track A`: Built `sdk/agentscope/patch.py` implementing `agentscope.patch(openai)` targeting OpenAI sync and async completion calls per RULES.md §2 Decision 6.
- `Track A`: Created `sdk/agentscope/__init__.py` exposing clean SDK entry points (`Span`, `Trace`, `TokenUsage`, `SpanStatus`, `trace`, `LangGraphAdapter`, `patch`).
- `Track A`: Added `sdk/pyproject.toml` to make `agentscope-sdk` an editable pip-installable package.
- `Track A`: Updated `sdk/agentscope/adapters/langgraph.py` so `_persist_run` matches `AsyncBaseTracer` async interface.
- `Track A`: Updated `sdk/agentscope/sender.py` to dynamically evaluate `AGENTSCOPE_API_KEY` and `AGENTSCOPE_INGEST_URL` per request.
- `Track A`: Added `sdk/tests/test_patch.py` testing sync and async OpenAI patching, token extraction, and fail-silent error handling.
- `Track A`: Updated `sdk/tests/test_cross_path.py` verifying schema identity across `LangGraphAdapter`, `@trace` decorator, and `patch(openai)` LLM spans.
- `Track A`: Created `examples/langgraph_demo_agent/` containing `linear_agent.py` (sequential 3-node workflow), `branching_agent.py` (conditional routing workflow), `main.py`, `README.md`, and `test_demo_e2e.py`.

**Why:**
- Fulfills Build Plan §4 Track A Week 3 (`agentscope.patch(openai)` + cross-path schema identity verification) and Week 4 (`examples/langgraph_demo_agent/` linear + branching agent with `LangGraphAdapter`).
- Maps to PRD §6.1, FR-1, FR-2, and User Flows 1 & 2.

**Assumptions made (if any):**
- Assumed `Completions.create` and `AsyncCompletions.create` on `openai.resources.chat.completions` are the primary interception targets for OpenAI python client (v1.x).
- Assumed dynamic lookup of `AGENTSCOPE_API_KEY` and `AGENTSCOPE_INGEST_URL` in `sender.py` avoids import-time stale environment variable issues.

**Open questions / follow-ups (if any):**
- **M1 Checkpoint Blocker:** Track B's WebSocket relay (`backend/app/ws.py`) does not exist yet in the codebase. Track B's `POST /ingest` endpoint is live and verified accepting real spans, but without `backend/app/ws.py`, the live end-to-end WebSocket streaming to Track C's dashboard for milestone M1 cannot be completed until Track B builds the WS relay. This is a Track B dependency gap and has been logged accordingly per INSTRUCTIONS.md §4.

**Tests added/run:**
- `sdk/tests/test_patch.py`: Verified sync and async OpenAI client patching, token usage parsing, error status recording, and fail-silent execution.
- `sdk/tests/test_cross_path.py`: Verified structural and schema identity across decorator, adapter, and patch integration paths.
- `examples/langgraph_demo_agent/test_demo_e2e.py`: Verified linear and branching demo agents send valid spans to real `POST /ingest` endpoint and receive 200 OK acceptance.
- All 8 SDK unit tests and 1 E2E integration test passed (100% pass rate).

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
