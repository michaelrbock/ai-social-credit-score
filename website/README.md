# TransAIUnion Site

This Site serves the leaderboard and two endpoints:

- `GET /api/leaderboard` returns public usernames, aggregate scores, prompt
  counts, and up to seven score snapshots per profile.
- `PUT /api/score` accepts a strict summary-only payload with a private bearer
  token; `DELETE /api/score` removes the profile and its history.

The Claude Code plugin calculates scores locally. The Site never accepts or
stores prompt text, rationales, paths, or session IDs. Token hashes, not bearer
tokens, are stored in D1. Its schema is in `db/schema.ts`; the generated
migration is in `drizzle/`.

The visual design is preserved in `public/`. The root route serves its
`index.html`; the leaderboard script reads the live API rather than sample
JSON.

For local development, use Node.js 22.13 or later. Install dependencies with
`npm ci`, run `npm run db:generate` after schema changes, then `npm run build`.
Apply the generated SQL migration to local D1 before `npm start` or `npm run
dev`. Deployment and D1 provisioning are managed by Sites using
`.openai/hosting.json`.
