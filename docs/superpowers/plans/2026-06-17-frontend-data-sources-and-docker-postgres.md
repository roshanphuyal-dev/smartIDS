# Frontend Data Sources and Docker Postgres Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frontend use a single, predictable data path and keep the database connection pinned to the Docker-provided PostgreSQL instance.

**Architecture:** Keep public pages static and auth pages public, keep protected dashboard pages behind the existing login gate, and route browser-side backend reads through same-origin frontend API proxies. Keep all DB reads/writes pointed at the Docker Postgres container (`localhost:8080` in dev) so the frontend and backend share the same source of truth.

**Tech Stack:** Next.js App Router, FastAPI, Postgres in Docker, Drizzle ORM, frontend API proxy routes, cookie-based auth.

---

### Task 1: Map current data paths

**Files:**
- Inspect: `frontend/src/app/(dashboard)/**/*`
- Inspect: `frontend/src/lib/backend/**/*`
- Inspect: `frontend/src/lib/db/**/*`
- Inspect: `frontend/src/app/api/**/*`

- [ ] **Step 1: List every frontend data source**

Document which pages read from:
- frontend proxy routes like `/api/dashboard/*`
- backend proxy routes like `/api/auth/*`
- backend-first fetch helpers with local DB fallback
- direct local DB helpers

- [ ] **Step 2: Confirm the current DB target**

Verify that dev `.env` files point to the Docker Postgres port (`localhost:8080`) and not a local standalone database.

- [ ] **Step 3: Record the result**

Summarize the current state in the repo notes so the next change set starts from a known baseline.

### Task 2: Consolidate browser data reads

**Files:**
- Modify: `frontend/src/lib/backend/dashboard.ts`
- Modify: `frontend/src/lib/backend/sessions.ts`
- Modify: `frontend/src/lib/backend/threats.ts`
- Modify: `frontend/src/lib/backend/blocked-ips.ts`
- Modify: `frontend/src/lib/backend/api-keys.ts`
- Modify: `frontend/src/app/api/**/route.ts`
- Modify: dashboard pages under `frontend/src/app/(dashboard)/**`

- [ ] **Step 1: Keep browser reads same-origin**

Route browser-side dashboard/auth reads through frontend `/api/*` proxies instead of direct backend URLs.

- [ ] **Step 2: Keep server-side reads auth-safe**

Preserve cookie forwarding in server components and route handlers so protected dashboard pages still resolve the current user correctly.

- [ ] **Step 3: Keep fallback behavior explicit**

Use local DB fallback only where it is intended, and make the fallback obvious in the UI when backend fetches fail.

### Task 3: Lock DB config to Docker Postgres

**Files:**
- Modify: `frontend/.env`
- Modify: `frontend/.env.example`
- Modify: `backend/.env`
- Modify: `backend/.env.example`
- Modify: `backend/docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Standardize dev connection strings**

Keep both frontend and backend pointed at the Docker Postgres service exposed on `localhost:8080`.

- [ ] **Step 2: Remove alternative local DB assumptions**

Delete or document any leftover config that implies a different PostgreSQL instance or port.

- [ ] **Step 3: Verify startup and login flow**

Confirm the frontend opens, the dashboard requires login, and protected pages load data through the shared Docker Postgres-backed backend.

