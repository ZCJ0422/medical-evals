# Medical Evals Workbench UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Next.js workbench into a data-dense, responsive evaluation console with an overview dashboard, searchable task management, guided evaluation creation, and more useful result summaries.

**Architecture:** Keep the existing API contract and session-token flow. Extract small reusable UI primitives under `frontend/components/`, keep API/domain types in `frontend/lib/`, and let each route compose those primitives. Derive dashboard metrics from `/api/evaluations`; never invent unavailable evaluation data.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS modules via the existing global stylesheet, Playwright.

## Global Constraints

- Use the Data-Dense Dashboard direction: professional, calm, scannable, with semantic status colors.
- Use an 8px spacing rhythm and responsive targets of 375px, 768px, 1024px, and 1440px.
- Keep primary interactive targets at least 44px and preserve visible keyboard focus states.
- Use 150–300ms opacity/transform transitions and respect `prefers-reduced-motion`.
- Do not add backend endpoints, database fields, provider SDKs, or heavyweight chart libraries.
- Do not expose API keys in rendered content, browser storage, or error messages.
- Every async region must support loading, empty, error, and success states.
- Status meaning must be communicated with text, not color alone.

---

### Task 1: Establish shared UI primitives and visual tokens

**Files:**
- Create: `frontend/components/ui.tsx`
- Create: `frontend/components/icons.tsx`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/layout.tsx`
- Test: `frontend/tests/ui-primitives.spec.ts`

**Interfaces:**
- `StatusBadge({ status }: { status: TaskStatus | string })` renders a text-labelled status with semantic class names.
- `ProgressBar({ value, label }: { value: number; label?: string })` clamps values to 0–100 and exposes `aria-valuenow`.
- `MetricCard({ label, value, detail?, tone? }: ...)` renders a KPI card without assuming trend data.
- `EmptyState({ title, body, action? }: ...)` renders a useful empty state.
- `InlineAlert({ tone, children }: ...)` renders `role="alert"` for errors and `role="status"` for success/info.
- `Skeleton({ className? }: ...)` reserves layout space during loading.

- [ ] **Step 1: Add failing Playwright assertions for shared semantics.**

Add tests that mount existing pages and assert that buttons have visible labels, progress exposes `aria-valuenow`, and reduced-motion CSS is present in the document stylesheet.

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `npm run test:e2e -- ui-primitives.spec.ts`

Expected: FAIL because the new semantic components and selectors do not exist.

- [ ] **Step 3: Implement the primitives and tokens.**

Define semantic CSS variables for canvas, surface, ink, muted, border, primary, success, warning, danger, and focus ring. Add focus-visible styles, button hover/pressed states, reduced-motion overrides, responsive gutters, and inline SVG icons for navigation/search/filter/arrow/check/trash/report.

- [ ] **Step 4: Run the focused test and build.**

Run: `npm run test:e2e -- ui-primitives.spec.ts && npm run typecheck`

Expected: PASS and no TypeScript errors.

- [ ] **Step 5: Commit the shared layer.**

```bash
git add frontend/components frontend/app/globals.css frontend/app/layout.tsx frontend/tests/ui-primitives.spec.ts
git commit -m "feat: add workbench ui primitives"
```

### Task 2: Upgrade the application shell and overview dashboard

**Files:**
- Create: `frontend/components/app-shell.tsx`
- Create: `frontend/components/page-header.tsx`
- Create: `frontend/components/dashboard-widgets.tsx`
- Modify: `frontend/app/app/layout.tsx`
- Modify: `frontend/app/app/page.tsx`
- Modify: `frontend/lib/types.ts`
- Test: `frontend/tests/dashboard.spec.ts`

**Interfaces:**
- `AppShell` owns responsive navigation, active route state, locale toggle, and logout.
- `DashboardStats` is derived from `TaskSummary[]` with `{ total, running, completed, failed, passRate: number | null }`.
- Dashboard widgets accept task data and render a real-data state or explicit empty state.

- [ ] **Step 1: Add failing dashboard tests.**

Mock `GET /api/evaluations` with no tasks and with queued/running/completed tasks. Assert the KPI labels, running task panel, recent task links, quick-start copy, and the absence of fabricated percentage trends when no result score exists.

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `npm run test:e2e -- dashboard.spec.ts`

Expected: FAIL because the dashboard still renders only the empty state.

- [ ] **Step 3: Implement the shell and dashboard.**

Move the current sidebar behavior into `AppShell`; add a compact mobile header and keep route-driven active navigation. Replace the dashboard page with a header, four KPI cards, running-now panel, recent evaluations panel, and three-step quick start. Compute only counts available from task summaries and show `—` when pass-rate data is unavailable.

- [ ] **Step 4: Run focused tests and responsive build checks.**

Run: `npm run test:e2e -- dashboard.spec.ts && npm run typecheck && npm run build`

Expected: PASS; desktop and mobile routes compile.

- [ ] **Step 5: Commit the dashboard.**

```bash
git add frontend/components frontend/app/app/layout.tsx frontend/app/app/page.tsx frontend/lib/types.ts frontend/tests/dashboard.spec.ts
git commit -m "feat: add evaluation workbench dashboard"
```

### Task 3: Replace the task card list with searchable evaluation management

**Files:**
- Create: `frontend/components/evaluation-filters.tsx`
- Create: `frontend/components/evaluation-table.tsx`
- Modify: `frontend/app/app/evaluations/page.tsx`
- Modify: `frontend/lib/types.ts`
- Test: `frontend/tests/evaluation-list.spec.ts`

**Interfaces:**
- `EvaluationFilters({ query, status, onQueryChange, onStatusChange })` is a controlled search/filter toolbar.
- `filterTasks(tasks, query, status): TaskSummary[]` is a pure helper used by the page and tests.
- `EvaluationTable({ tasks, onDelete })` renders desktop table semantics and mobile card fallback.

- [ ] **Step 1: Add failing tests for search, status filters, empty and delete feedback.**

Mock tasks with different names/statuses/models. Assert search matches task name, model, dataset and ID; status filters update counts; no-match state offers a clear reset; delete confirmation and success feedback are announced through `aria-live`.

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `npm run test:e2e -- evaluation-list.spec.ts`

Expected: FAIL because the page has no filter toolbar or table.

- [ ] **Step 3: Implement pure filtering and responsive task presentation.**

Keep the existing 3-second polling. Add loading skeletons that preserve the task region height, summary counts, controlled query/status state, table columns for name/target/judge/dataset/status/progress/actions, and a mobile card layout under 768px. Use `StatusBadge` and `ProgressBar`; preserve the existing confirmation before DELETE.

- [ ] **Step 4: Run focused tests and typecheck.**

Run: `npm run test:e2e -- evaluation-list.spec.ts && npm run typecheck`

Expected: PASS with no API contract changes.

- [ ] **Step 5: Commit task management.**

```bash
git add frontend/components frontend/app/app/evaluations/page.tsx frontend/lib/types.ts frontend/tests/evaluation-list.spec.ts
git commit -m "feat: add evaluation search and filtering"
```

### Task 4: Convert new evaluation into a four-step wizard

**Files:**
- Create: `frontend/components/evaluation-wizard.tsx`
- Modify: `frontend/app/app/evaluations/new/page.tsx`
- Modify: `frontend/lib/types.ts`
- Test: `frontend/tests/evaluation-wizard.spec.ts`

**Interfaces:**
- `WizardDraft` contains the existing create payload fields, with secrets held only in React state until submission.
- `getWizardSteps(draft): WizardStep[]` returns Dataset, Models, Run options, and Review steps.
- `validateWizardStep(step, draft): string[]` returns field-level errors before allowing Next.

- [ ] **Step 1: Add failing tests for step progression and conditional Judge fields.**

Assert that the user cannot advance without a dataset/model, HealthBench reveals Judge fields, MedQA does not require them, Back preserves entered values, Review shows a redacted summary, and submit calls preflight before create.

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `npm run test:e2e -- evaluation-wizard.spec.ts`

Expected: FAIL because the current page is a single long form.

- [ ] **Step 3: Implement the controlled wizard.**

Split the existing form into four field groups. Keep target/Judge API keys in component state and never echo their values in Review. Use visible labels, helper text, inline errors, step indicator, Back/Next buttons, and a final preflight status block. Preserve current `POST /api/evaluations/preflight` then `POST /api/evaluations` behavior.

- [ ] **Step 4: Run focused tests and build.**

Run: `npm run test:e2e -- evaluation-wizard.spec.ts && npm run typecheck && npm run build`

Expected: PASS; no secrets appear in DOM text or browser storage.

- [ ] **Step 5: Commit the wizard.**

```bash
git add frontend/components frontend/app/app/evaluations/new/page.tsx frontend/lib/types.ts frontend/tests/evaluation-wizard.spec.ts
git commit -m "feat: add guided evaluation wizard"
```

### Task 5: Upgrade results into an accessible analysis summary

**Files:**
- Create: `frontend/components/score-bars.tsx`
- Create: `frontend/components/result-summary.tsx`
- Modify: `frontend/app/app/evaluations/[id]/results/page.tsx`
- Test: `frontend/tests/results.spec.ts`

**Interfaces:**
- `ResultSummary` extends the current response with optional `name`, `status`, `dataset_version_id`, `target_model_id`, `judge_model_id`, `created_at`, and `completed_at`; optional fields must remain optional.
- `ScoreBars({ scores }: { scores: Record<string, number> })` renders accessible horizontal bars plus text values.
- `ReportButton({ taskId }: { taskId: string })` owns generate loading/success/error state.

- [ ] **Step 1: Extend failing result tests.**

Mock a result with dimensions/errors and assert KPI cards, accessible score bars, error counts, task metadata, report loading feedback, and empty states. Assert that score remains readable without relying on color.

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `npm run test:e2e -- results.spec.ts`

Expected: FAIL because the current result page has plain score rows and no report feedback state.

- [ ] **Step 3: Implement result components.**

Add header metadata, KPI grid, horizontal score bars backed by a table-like accessible structure, error breakdown, run summary, and report action. Only render optional metadata when present. Disable the report button while generating and announce success/failure.

- [ ] **Step 4: Run focused tests and build.**

Run: `npm run test:e2e -- results.spec.ts && npm run typecheck && npm run build`

Expected: PASS and a production build without new dependencies.

- [ ] **Step 5: Commit result analysis.**

```bash
git add frontend/components frontend/app/app/evaluations/[id]/results/page.tsx frontend/tests/results.spec.ts
git commit -m "feat: improve evaluation result analysis"
```

### Task 6: Final responsive, accessibility, and regression pass

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/tests/smoke.spec.ts`
- Modify: `frontend/tests/auth-and-evaluation.spec.ts`
- Modify: `frontend/tests/bilingual-catalog.spec.ts`
- Create: `frontend/tests/workbench-responsive.spec.ts`

- [ ] **Step 1: Add responsive and reduced-motion coverage.**

Test at 375px, 768px, and 1440px that the shell has no horizontal overflow, mobile navigation remains reachable, table cards fit the viewport, and reduced-motion removes nonessential transitions.

- [ ] **Step 2: Run the full frontend checks.**

Run: `npm run typecheck && npm run build && npm run test:e2e`

Expected: PASS for all existing and new tests.

- [ ] **Step 3: Perform the manual checklist.**

Verify keyboard Tab order, visible focus rings, form error recovery, API key redaction, status text plus semantic color, empty/loading/error/success states, and report action feedback. Check the 375px layout in portrait and a desktop layout at 1440px.

- [ ] **Step 4: Commit the final polish.**

```bash
git add frontend
git commit -m "chore: verify workbench ui refresh"
```

## Plan Self-Review

- Spec coverage: dashboard, task filtering, guided creation, results analysis, responsive behavior, accessibility, motion, async states, API boundaries, and tests are covered by Tasks 1–6.
- Placeholder scan: no unfinished placeholder markers or vague implementation steps are used.
- Type consistency: all component signatures use `TaskSummary`, `TaskStatus`, `DatasetVersion`, `WizardDraft`, and optional `ResultSummary` fields defined in this plan or the existing `frontend/lib/types.ts`.
- Scope: all work remains in the frontend and does not require backend changes or new runtime dependencies.
