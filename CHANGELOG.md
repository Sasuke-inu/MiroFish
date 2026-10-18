# Changelog

All notable changes to this fork (`Sasuke-inu/MiroFish`) are documented in this file.
Upstream history lives in [666ghj/MiroFish](https://github.com/666ghj/MiroFish).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Self-hosted local graph stack (Graphiti + Neo4j, CPU embeddings) selected with
  `GRAPH_PROVIDER=graphiti`; Zep Cloud stays the default (`GRAPH_PROVIDER=zep`).
  See `ZEP-REPLACEMENT-ZH-TW.md`.
- Local Docker install (`docker-compose.local.yml`, `Dockerfile.local`) bound to
  `127.0.0.1` (UI on port 3100, API on 5001), plus Windows `Start-MiroFish.cmd` /
  `Stop-MiroFish.cmd`. See `INSTALLATION-ZH-TW.md`.
- Optional self-hosted Firecrawl source collection (`FIRECRAWL_*` settings) with
  per-job and daily page caps and no automatic Cloud fallback.
  See `FIRECRAWL-INTEGRATION-ZH-TW.md`.
- Research workbench (overview / data / results), provider settings UI, saved
  report reader, replay, and zh-TW locale (`locales/zh-TW.json`).
- `GET /api/session` endpoint that issues the CSRF token used by the frontend.
- Persistent report version ledger (`report_versions`; numbers are never reused)
  and latest-observed evidence pointer (`latest_version_id` in the API).
- Simulation completion receipts recording exit reason, actual rounds and
  cumulative simulated hours; `graph_update_status` on runs.

### Changed

- Every `/api` route now requires a local trusted origin, and state-changing
  requests must send the `X-MiroFish-CSRF` header; CORS is narrowed from `*` to a
  local allow-list. (R01)
- `graph_ready` is only true when a graph update was requested and finished
  successfully; interviews no longer depend on it. (R03)
- Simulation logs are read with a byte-offset cursor; incomplete trailing lines
  are never skipped and corrupt lines are recorded as `log_gaps`. (R07)
- Dockerfile installs vendored packages before `uv sync`, and pins Node 22. (R05, R16)
- Supported Node.js range declared as `^22.22.2 || ^24.15.0 || >=26.0.0`. (R16)
- Backend test suite is hermetic: Zep contract tests pin `GRAPH_PROVIDER=zep`, and
  the POSIX-only SQLite file-replacement test is skipped on Windows.

### Fixed

- Deleting a report that is still generating returns 409; reports missing
  sections are marked `NEEDS_REVIEW` instead of completed. (R04)
- Text chunking always moves forward and can no longer loop or silently drop text. (R06)
- Demo catalog opens installed demos by saved project id and installs only on an
  explicit request. (R09)
- Partial reports render each saved section independently. (R10)
- Locating saved events keeps the original replay and report selection. (R11)
- Report setup failures clean up their claim, and a failed report with no output
  can be retried without `force`. (R12)
- Simulation `platform` is validated (`twitter` / `reddit`) and simulation SQLite
  is opened read-only. (R13)
- Per-report console log handlers are isolated and always removed. (R14)
- Runs missing `simulated_hours` keep the previous value instead of resetting. (R15)
- Download fallback uses an in-memory buffer instead of leaking temp files. (R17)

Full review findings and verification: `CODE-REVIEW-2026-10-18.md` and
`IMPLEMENTATION-2026-10-18.md`.
