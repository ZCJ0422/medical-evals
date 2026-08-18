# Apple-Inspired Frontend Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the Medical Evals frontend with a calm Apple-inspired visual system, responsive layout, and accessible motion while preserving current behavior and API contracts.

**Architecture:** Keep the existing Next.js App Router and component boundaries. Centralize visual tokens, surfaces, interaction states, responsive rules, and reduced-motion fallbacks in `app/globals.css`; make only small JSX changes where semantic wrappers or labels improve the visual hierarchy.

**Tech Stack:** Next.js 15, React 19, TypeScript, plain CSS, existing SVG icon components, Playwright.

## Global Constraints

- Modify only frontend source and frontend documentation for this refresh.
- Keep all fetch calls, route paths, event handlers, task status semantics, and bilingual strings unchanged.
- Use the platform system font stack; do not add a font dependency.
- Use transform and opacity for motion; include `prefers-reduced-motion`, `prefers-reduced-transparency`, and `prefers-contrast` fallbacks.
- Keep visible keyboard focus styles and at least 44px interactive targets.

---

### Task 1: Establish the visual foundation

**Files:**
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consumes: existing class names used by all frontend components.
- Produces: shared color, material, spacing, type, focus, motion, and responsive tokens used by later tasks.

- [ ] **Step 1: Replace the current root tokens and body defaults** with pale blue-gray canvas, deep ink text, restrained violet/teal accents, system font stack, and CSS custom properties for radius, shadow, and transition values.
- [ ] **Step 2: Add shared material and motion utilities** for surfaces, entry transitions, hover/active states, visible focus, skeleton shimmer, and status emphasis. Use only transform/opacity for animated movement.
- [ ] **Step 3: Add accessibility media queries** so reduced motion removes movement, reduced transparency uses opaque surfaces, and increased contrast adds defined borders and stronger text.
- [ ] **Step 4: Add responsive breakpoints** for the app shell, page padding, tables, forms, dashboard grids, and action groups at approximately 900px and 640px.
- [ ] **Step 5: Run `npm run typecheck`** from `frontend/` to ensure the CSS-only foundation did not affect the app.

### Task 2: Refine the authenticated shell and navigation

**Files:**
- Modify: `frontend/components/app-shell.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consumes: existing `usePathname`, `useLocale`, auth, and navigation behavior.
- Produces: semantic shell classes for frosted sidebar, active navigation, workspace footer, and page entry.

- [ ] **Step 1: Add semantic wrapper classes** around the sidebar brand, navigation, and footer without changing links, labels, or click handlers.
- [ ] **Step 2: Style the sidebar as a layered material** with a translucent background, subtle edge highlight, active item indicator, and responsive compact layout.
- [ ] **Step 3: Add pointer-down feedback** to navigation links, locale toggle, logout, and brand while preserving keyboard focus rings.
- [ ] **Step 4: Verify the shell still redirects unauthenticated users** by running the existing auth smoke test if the local test server is available.

### Task 3: Refine dashboard hierarchy and cards

**Files:**
- Modify: `frontend/app/app/page.tsx`
- Modify: `frontend/components/page-header.tsx`
- Modify: `frontend/components/dashboard-widgets.tsx`
- Modify: `frontend/components/ui.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consumes: existing dashboard data, translation keys, loading states, and task components.
- Produces: clearer page header, metric cards, running/recent panels, empty state, and quick-start hierarchy.

- [ ] **Step 1: Add presentational classes and accessible status semantics** to the page header, metric cards, panels, and quick-start steps without changing data calculations.
- [ ] **Step 2: Style the dashboard using a calm primary metric, secondary panels, and a lighter quick-start surface** with consistent 14–24px radii and layered shadows.
- [ ] **Step 3: Add restrained staggered entry classes** for the first visible dashboard regions and skeleton states; disable movement under reduced motion.
- [ ] **Step 4: Run the dashboard Playwright smoke test** and confirm the new evaluation CTA and empty/loading states remain reachable.

### Task 4: Refine evaluation list, filters, and task actions

**Files:**
- Modify: `frontend/app/app/evaluations/page.tsx`
- Modify: `frontend/components/evaluation-filters.tsx`
- Modify: `frontend/components/evaluation-table.tsx`
- Modify: `frontend/components/ui.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consumes: existing filtering, delete, cancel, retry, status badge, and progress behavior.
- Produces: responsive evaluation table/card layout, clearer filters, and Apple-like action feedback.

- [ ] **Step 1: Add semantic grouping around list summary, filters, and table actions** without changing callbacks or confirmation behavior.
- [ ] **Step 2: Style filters as a compact translucent control group** with 44px fields, clear labels, and visible focus.
- [ ] **Step 3: Style table rows, progress bars, status badges, icon buttons, and text actions** with hover/active states and enough contrast.
- [ ] **Step 4: Add the narrow-screen card transformation** using existing `data-label` attributes so evaluation rows remain readable without horizontal scrolling.
- [ ] **Step 5: Run the evaluation list and results Playwright tests** to verify viewing, retrying, cancelling, and deleting remain wired correctly.

### Task 5: Refine new-evaluation form and result-facing shared surfaces

**Files:**
- Modify: `frontend/app/app/evaluations/new/page.tsx`
- Modify: `frontend/components/evaluation-wizard.tsx`
- Modify: `frontend/app/app/evaluations/[id]/results/page.tsx`
- Modify: `frontend/components/result-summary.tsx`
- Modify: `frontend/components/score-bars.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consumes: existing form state, API submission, result data, error handling, and translations.
- Produces: clearer step grouping, form feedback, result hierarchy, and responsive score presentation.

- [ ] **Step 1: Add presentational grouping and helper-text classes** to the wizard fields while preserving all names, values, validation, and submit behavior.
- [ ] **Step 2: Style the wizard as a sequence of calm sections** with a distinct primary submit action and clear loading/error/success feedback.
- [ ] **Step 3: Style result summary and score bars** so aggregate score, dimensions, failures, and retry/view actions have distinct visual priority.
- [ ] **Step 4: Run form and results Playwright tests** and confirm no API contract or route changed.

### Task 6: Final verification and review

**Files:**
- Verify: `frontend/app/globals.css`
- Verify: all modified frontend files above

- [ ] **Step 1: Run `npm run typecheck`** from `frontend/` and confirm it passes.
- [ ] **Step 2: Run `npm run build`** from `frontend/` and confirm the production build passes.
- [ ] **Step 3: Run `npm run test:e2e`** from `frontend/` when the local backend/test server is available; record any environment-only blockers separately.
- [ ] **Step 4: Review the diff** for accidental backend changes, API changes, missing focus states, low contrast, or motion that ignores reduced-motion preferences.
- [ ] **Step 5: Report the exact files changed and verification results** without claiming tests that were not run.
