# Demo Data Policy

## Boundary

`src/data/demoSeed.ts` is a demo fixture asset only. It contains invented events,
causal chains, end-of-day summaries, liquidation state, market tape alerts, and
audit records.

Production pages must consume REST snapshots, WebSocket events, or explicit empty
states. They must not import demo fixtures to fill missing Web API data.

## Import Rule

- Do not import from `src/data` in production page, component, state, API, or
  WebSocket code.
- Do not import `src/data/demoSeed.ts` directly from production runtime code.
- Use `src/data/demoOnly.ts` only for isolated demo, design review, or fixture
  tooling code.

The root `src/data/index.ts` barrel intentionally exports nothing. This prevents
accidental imports such as `import { demoMarket } from "../data"` from compiling.

## Missing Backend Capability

When a real API response does not include a field or capability, show the
documented empty state or `N/A`. Do not backfill with demo causal chains, demo
risk state, demo leaderboard-style market claims, or invented audit records.
