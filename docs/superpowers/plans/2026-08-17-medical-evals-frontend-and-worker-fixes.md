# Medical Evals Frontend and Worker Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复医疗评测工作台的完整中英文切换、当前 UI 对应的 E2E 测试契约，以及 Worker 的 cwd 独立数据路径。

**Architecture:** 继续使用现有 React Context 做前端本地化；不重构页面，只把用户可见固定文案集中到字典并在组件中消费。后端通过模块位置解析项目根目录，避免依赖启动目录；测试分别覆盖本地化、当前向导交互和 cwd 变化。

**Tech Stack:** Next.js 15、React 19、TypeScript、Playwright、FastAPI、Python 3.12、pytest、uv。

## Global Constraints

- 不覆盖 `medical-evals` 当前已有未提交修改。
- 不改变 API key 加密、任务状态机和评分公式。
- 测试只使用占位凭据，不发送真实 API key。
- 所有生产代码修改前先添加并运行对应失败测试。

---

### Task 1: Make Registry data paths independent of cwd

**Files:**
- Create: `medical-evals/backend/medical_evals_api/paths.py`
- Modify: `medical-evals/backend/medical_evals_api/evaluator_adapter.py`
- Test: `medical-evals/backend/tests/test_real_worker.py`
- Test: `medical-evals/backend/tests/test_healthbench_real_worker.py`

**Interfaces:**
- Produces `project_root() -> Path` and `registry_data_path(*parts: str) -> Path`.
- Existing adapters continue to receive the same `EvaluationTask` and return the same `EvaluationRunResult`.

- [ ] **Step 1: Add a cwd-independent failing test**

Add a test that changes cwd to `tmp_path` before running a MedQA Worker task with `max_samples=1`, and assert the task completes and saves a result. Add the equivalent cwd change to the HealthBench smoke test.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```bash
cd medical-evals/backend
PYTHONPATH=.:.. UV_CACHE_DIR=/private/tmp/medical-evals-uv-cache uv run pytest -q tests/test_real_worker.py tests/test_healthbench_real_worker.py
```

Expected: the tests fail because `registry/data/...` is resolved from the temporary cwd.

- [ ] **Step 3: Implement the path helper and replace relative paths**

Use `Path(__file__).resolve().parents[2]` as the `medical-evals` project root and have the adapter load `registry_data_path("medical_medqa", "dev.jsonl")` and `registry_data_path("medical_healthbench", "smoke.jsonl")`.

- [ ] **Step 4: Run focused tests and the full backend suite**

Run the focused command above, then:

```bash
cd medical-evals/backend
PYTHONPATH=.:.. UV_CACHE_DIR=/private/tmp/medical-evals-uv-cache uv run pytest -q
```

Expected: all backend tests pass.

- [ ] **Step 5: Commit the isolated backend fix**

```bash
git add backend/medical_evals_api/paths.py backend/medical_evals_api/evaluator_adapter.py backend/tests/test_real_worker.py backend/tests/test_healthbench_real_worker.py
git commit -m "fix: resolve evaluator data paths from project root"
```

### Task 2: Complete locale coverage and synchronize document language

**Files:**
- Modify: `medical-evals/frontend/lib/i18n.tsx`
- Modify: `medical-evals/frontend/app/layout.tsx`
- Modify: `medical-evals/frontend/app/login/page.tsx`
- Modify: `medical-evals/frontend/app/app/page.tsx`
- Modify: `medical-evals/frontend/app/app/evaluations/page.tsx`
- Modify: `medical-evals/frontend/app/app/evaluations/new/page.tsx`
- Modify: `medical-evals/frontend/components/app-shell.tsx`
- Modify: `medical-evals/frontend/components/evaluation-wizard.tsx`
- Modify: `medical-evals/frontend/components/evaluation-filters.tsx`
- Modify: `medical-evals/frontend/components/evaluation-table.tsx`
- Test: `medical-evals/frontend/tests/bilingual-catalog.spec.ts`

**Interfaces:**
- `useLocale().t(key)` remains the only component-facing translation API.
- `LocaleProvider` updates the document language attribute whenever locale changes.

- [ ] **Step 1: Extend the bilingual E2E assertion before implementation**

Update the bilingual test to assert that after clicking `中文`, the new evaluation page exposes the Chinese title `创建测评`, a Chinese dataset label, and `document.documentElement.lang === "zh-CN"`; add an English toggle assertion for `lang === "en"`.

- [ ] **Step 2: Run the focused E2E test and capture the red result**

Run `npm run test:e2e -- tests/bilingual-catalog.spec.ts`. In environments where Chromium cannot launch, record the sandbox launch error; the test must still be syntactically valid and target the intended behavior.

- [ ] **Step 3: Add dictionary keys and route all visible fixed copy through `t`**

Add keys for wizard steps, headings, descriptions, form labels, validation messages, list/filter/status labels, empty states, delete/creation notices, login busy text, and dashboard quick-start copy. Add `name` attributes to the dataset select and relevant inputs while preserving accessible labels.

- [ ] **Step 4: Synchronize `html lang` and verify the locale behavior**

Use an effect in `LocaleProvider` to set `document.documentElement.lang` to `zh-CN` or `en` after locale changes. Keep the server-safe initial document language as `en`.

- [ ] **Step 5: Run frontend static verification**

Run:

```bash
cd medical-evals/frontend
npm run typecheck
npm run build
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit the locale fix**

```bash
git add frontend/lib/i18n.tsx frontend/app frontend/components frontend/tests/bilingual-catalog.spec.ts
git commit -m "fix: localize medical eval workbench flows"
```

### Task 3: Align E2E tests with the four-step wizard

**Files:**
- Modify: `medical-evals/frontend/tests/auth-and-evaluation.spec.ts`
- Modify: `medical-evals/frontend/tests/results.spec.ts`
- Modify: `medical-evals/frontend/tests/smoke.spec.ts`
- Modify: `medical-evals/frontend/playwright.config.ts`

**Interfaces:**
- Tests use current visible labels and table rows.
- Playwright configuration can reuse already-running local services and documents the required API service.

- [ ] **Step 1: Rewrite the create-flow tests against current labels**

Select a dataset through the combobox, click exact `Next` buttons for steps 1–3, fill `Target API Key` with `test-key`, and assert `Evaluation queued`. For HealthBench, fill the conditional Judge fields. Use table-row locators for queued-task assertions.

- [ ] **Step 2: Run the rewritten tests before changing production behavior**

Run `npm run test:e2e -- tests/auth-and-evaluation.spec.ts tests/results.spec.ts tests/smoke.spec.ts`. Expected in the current sandbox is a Chromium launch failure; in a browser-capable environment failures should now reflect only real application behavior.

- [ ] **Step 3: Add stable selectors only where semantic selectors are insufficient**

Keep `getByRole`/`getByLabel` as the default. Use the dataset select `name="dataset_version_id"` and `name` attributes for API fields only to make the current contract explicit, without adding selectors that encode implementation details.

- [ ] **Step 4: Run typecheck and build after test-contract changes**

Run `npm run typecheck && npm run build` and confirm exit 0.

- [ ] **Step 5: Commit the E2E contract update**

```bash
git add frontend/tests frontend/playwright.config.ts frontend/components/evaluation-wizard.tsx
git commit -m "test: align workbench e2e flows with current wizard"
```

### Task 4: Final verification and report

**Files:**
- No production files unless a verification failure requires a targeted correction.

- [ ] **Step 1: Run the full backend test suite**

Run the `PYTHONPATH=.:.. ... uv run pytest -q` command from Task 1 and record pass/fail counts.

- [ ] **Step 2: Run frontend typecheck and production build**

Run `npm run typecheck` and `npm run build` from `medical-evals/frontend`.

- [ ] **Step 3: Run the full Playwright suite**

Run `npm run test:e2e`; distinguish browser-launch infrastructure failures from application assertion failures.

- [ ] **Step 4: Inspect the final diff and repository status**

Run `git diff --check` and `git status --short` in `medical-evals`; ensure no unrelated existing modifications were overwritten.

- [ ] **Step 5: Report evidence and remaining environment limitations**

Report exact command results, any CSS warnings, the Chromium sandbox limitation if still present, and whether the local queued smoke record remains.
