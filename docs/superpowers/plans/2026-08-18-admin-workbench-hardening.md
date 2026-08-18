# Admin Workbench Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make the medical-evaluation workbench observable during execution, usable for large result sets, and safer to operate without changing retry or resume behavior.

**Architecture:** Extend the task/result API with immutable task metadata and progress stage information. Reuse the existing artifact files as the source for logs and samples, then add focused client-side polling, pagination, filtering, and detailed HealthBench rubric views.

**Tech Stack:** FastAPI, SQLite, Pydantic, Next.js, React, TypeScript, CSS.

**Spec:** User-approved audit from 2026-08-18; retry and checkpoint-resume interaction are explicitly out of scope.

## Global Constraints

- Do not change retry naming or checkpoint-resume behavior.
- Keep model API keys out of API responses, logs, and browser storage.
- Keep artifact paths derived from one shared configuration value.
- Add tests before behavior changes and run the backend suite plus frontend build/typecheck.

### Task 1: Task details and artifact access

**Files:** `backend/medical_evals_api/schemas/common.py`, `backend/medical_evals_api/services/results.py`, `backend/medical_evals_api/routes/results.py`, `backend/medical_evals_api/repositories/tasks.py`, backend tests.

- [ ] Add task metadata, stage, timestamps, and actionable error detail to result responses.
- [ ] Read samples and logs through a shared artifact-root resolver.
- [ ] Test running-task detail responses and artifact-root consistency.

### Task 2: Worker stages and operational errors

**Files:** `backend/medical_evals_api/evaluator_adapter.py`, `backend/medical_evals_api/worker.py`, backend tests.

- [ ] Persist the current execution stage with each progress update.
- [ ] Record safe, categorized failure detail and suggested recovery action.
- [ ] Test stage transitions and failure detail.

### Task 3: Results page observability

**Files:** `frontend/app/app/evaluations/[id]/results/page.tsx`, `frontend/components/result-summary.tsx`, `frontend/lib/api.ts`, `frontend/lib/i18n.tsx`, `frontend/app/globals.css`.

- [ ] Allow queued and running tasks to open their details.
- [ ] Poll live task state and logs only while active.
- [ ] Add log follow mode, copy, download, stage, last-update, and actionable errors.

### Task 4: Scalable sample review

**Files:** `frontend/app/app/evaluations/[id]/results/page.tsx`, `frontend/lib/i18n.tsx`, `frontend/app/globals.css`.

- [ ] Page samples through the existing offset/limit endpoint.
- [ ] Filter failures, parse failures, and low-score HealthBench records.
- [ ] Display HealthBench rubric judgments and explanations in an expandable section.

### Task 5: Safety and interface polish

**Files:** `backend/medical_evals_api/config.py`, `backend/medical_evals_api/auth.py`, `frontend/components/app-shell.tsx`, `frontend/app/globals.css`, tests.

- [ ] Fail fast for insecure production configuration while preserving local development access.
- [ ] Add visible keyboard focus, skip navigation, long-text protections, and a refresh timestamp.
- [ ] Verify no API key is returned or logged.
