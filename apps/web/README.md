# apps/web — DeevAI frontend

Next.js 15 (App Router), TypeScript strict, Tailwind v3, dark-mode-first.

## Quickstart

```bash
cd apps/web
npm install
npm run dev
# → http://localhost:3000
```

## Notes

- Tailwind palette in `tailwind.config.ts` (custom `ink` neutral + `accent` teal — the brand palette).
- The `Wordmark` component (`components/wordmark.tsx`) is the single source of brand truth — three variants (`logo`, `text`, `editorial`).
- `next.config.ts` rewrites `/api/v1/*` to the FastAPI backend on `:8000` in dev. In prod the reverse proxy handles it.
- No shadcn/ui installed yet — added in Sprint 2 when we build the dashboard.
- No auth yet (Sprint 1.3). Pages like `/signin`, `/signup` are placeholders that 404 today.

## What's here today

- `app/page.tsx` — landing page with brand wordmark + early-access CTA
- `app/layout.tsx` — root layout, metadata, dark mode default
- `components/wordmark.tsx` — three-tier brand system
- `public/wordmark.svg` — vector logo (uses `currentColor` for theming)
