# Medical Evals Apple-Inspired Frontend Refresh

## Goal

Refresh the existing Medical Evals workbench UI so it feels calm, precise, and responsive in an Apple-inspired way while preserving the current routes, API behavior, bilingual copy, and task actions.

## Scope

- Restyle the authenticated application shell, dashboard, evaluation list, filters, form controls, cards, tables, badges, and result-facing shared UI.
- Add subtle, interruptible-feeling CSS feedback for press, hover, focus, loading, and page entry states.
- Add responsive behavior for narrow screens without changing data flow or API contracts.
- Respect `prefers-reduced-motion`, `prefers-reduced-transparency`, and `prefers-contrast`.
- Keep existing SVG icon components and existing component boundaries.

## Visual Direction

- Use the platform system font stack for familiar typography.
- Use a pale blue-gray canvas, white/frosted surfaces, deep ink text, and restrained violet/teal accents.
- Treat the sidebar and compact controls as translucent materials with `backdrop-filter`, while keeping primary content surfaces legible and mostly opaque.
- Use 14–24px radii, soft layered shadows, and subtle borders rather than heavy outlines.
- Use status text, icons, and color together so status is never communicated by color alone.

## Interaction and Motion

- Give buttons, links, rows, and icon controls immediate `:active` feedback on pointer-down.
- Use 160–280ms ease-out transitions for hover/focus and 300–420ms restrained page-entry transitions.
- Animate only opacity and transform for entry/feedback states; avoid decorative continuous motion.
- Replace entry movement with a short opacity transition when reduced motion is enabled.
- Preserve visible keyboard focus rings and minimum 44px interactive targets.

## Implementation Boundaries

- Modify only frontend files for the visual refresh.
- Keep all fetch calls, route paths, event handlers, and task status semantics unchanged.
- Prefer CSS class updates and small presentational JSX changes over component rewrites.
- Verify with `npm run typecheck`, `npm run build`, and the existing Playwright smoke suite where the local environment permits.
