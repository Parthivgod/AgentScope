# Contributing to AgentScope

Thank you for contributing! To ensure smooth collaboration across our parallel tracks (SDK, Backend, Dashboard), please follow these setup instructions.

## One-Time Setup

AgentScope heavily relies on append-only tracking files (`CHANGELOG.md` and `docs/future-work.md`). To prevent constant merge conflicts when multiple tracks update these files simultaneously, we use a custom Git merge driver.

Run this command once after cloning the repository:

```bash
git config merge.union.driver true
```

This tells Git to use the `union` merge strategy for files specified in `.gitattributes`, automatically keeping both sides of a modification instead of flagging a conflict.

## Workflow

1. Read `RULES.md` and `INSTRUCTIONS.md` before starting any work.
2. Ensure you have Docker Desktop running for the backend infrastructure.
3. Use the dev-preflight scripts to verify your environment before running agents.
