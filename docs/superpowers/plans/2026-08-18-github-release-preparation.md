# GitHub Release Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository safe, reproducible, and understandable for a first GitHub submission without committing local data, runtime state, build outputs, or credentials.

**Architecture:** Preserve source code, registry fixtures, tests, and documentation in Git. Treat full HealthBench JSONL files, SQLite state, browser/build output, evaluation artifacts, and API credentials as local inputs; document how to supply them locally.

**Tech Stack:** Python/uv, FastAPI, Next.js, Playwright, GitHub Git.

## Global Constraints

- Do not alter evaluation, worker, retry, or resume behavior.
- Do not delete existing local datasets or databases; ignore them only.
- Do not include model outputs, complete protected benchmark data, API keys, or build artifacts in Git.
- Do not push to GitHub unless the user explicitly asks.

---

### Task 1: Make local runtime and dataset boundaries explicit

**Files:**
- Modify: `.gitignore`
- Create: `backend/.env.example`
- Test: Git ignore checks

- [x] Add ignore rules for `dataset/HealthBench/`, `backend/backend/`, and `frontend/.next-build/`.
- [x] Add a safe, value-free backend environment template with only configuration names.
- [x] Verify `git check-ignore -v` identifies each local-only path.

### Task 2: Document reproducible setup and data handling

**Files:**
- Modify: `README.md`

- [x] Explain local workbench setup with `uv sync`, API, worker, and frontend commands.
- [x] State that full HealthBench JSONL data is local-only and where it must be placed.
- [x] State that credentials belong in ignored environment variables and are never committed.

### Task 3: Run pre-submit checks and report the commit boundary

**Files:**
- Verify: backend tests, frontend typecheck/build, Git status

- [x] Run backend tests from `backend/` with `PYTHONPATH=..:. .venv/bin/pytest -q`.
- [x] Run `npm run build`, `npm run typecheck`, and `npm run test:e2e` from `frontend/`.
- [x] Run `git diff --check`, review staged candidates, and report what remains intentionally untracked.

### P0 release-gate verification — 2026-08-25

- [x] Verify the `main` baseline in an isolated clean worktree.
- [x] Root suite: 95 passed.
- [x] Backend suite: 101 passed.
- [x] Frontend typecheck and production build: passed.
- [x] Playwright browser suite: 10 passed.
- [x] Record the local-listener requirement for E2E (`127.0.0.1:3000` and `127.0.0.1:8000`).
