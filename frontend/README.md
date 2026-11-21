# Radar innowacji frontend

Polish web app of Radar innowacji using Next.js App Router, React, TypeScript and Tailwind CSS: home page, chat with the submission creator, Moje sprawy, the innovation base, pilot partner sign-up, contact and admin views.

## Development

```sh
pnpm install
pnpm dev
```

Open http://localhost:3000 with the backend running on port 8000, or set the server-side `BACKEND_URL` before starting Next.js.
The browser talks to FastAPI through the allowlisted same-origin proxy `app/api/backend/[...path]/route.ts` (session cookie and CSRF header) and the `/api/chat` rewrites.

Validate with:

```sh
pnpm exec next typegen
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

Frontend visual and interaction guidelines: [DESIGN-STYLE.md](DESIGN-STYLE.md).

## Docker Compose

From the repository root run `docker compose up --build -d` and open the frontend port from `.env` (`FRONTEND_PORT`, default 3000).

The image uses Next.js standalone output and runs as the unprivileged Node user.
`BACKEND_URL` controls the server-side rewrite at build time; change its Compose build argument and rebuild when changing the destination.
`NEXT_PUBLIC_API_BASE_URL` is the browser-facing backend URL and is also a build argument.
Neither value may contain secrets.
