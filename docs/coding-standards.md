# Coding Standards

Repository conventions for SmartIDS — how code is written, not how the system is designed (`docs/architecture.md`) or why (`docs/decisions.md`). Derived from `AGENTS.md`, `backend/AGENTS.md`, and observed code patterns.

---

## General

- Solve only the requested problem; avoid speculative abstractions and future-proofing not asked for.
- Keep modules isolated by responsibility: capture, parsing, session/flow management, feature extraction, ML, alerting, response handling stay in their own top-level packages (`packet_capture/`, `traffic_engine/`, `feature_engine/`, `ml/`, `threat_detection/`, `response_engine/`) — don't cross-import business logic between them beyond the documented pipeline handoffs (`docs/architecture.md`).
- Keep import paths aligned with actual folders; keep packet model types aligned with parser output (`AGENTS.md`, Known Footguns).
- Avoid printing in hot packet-processing paths except rate-limited debug output.
- Validate changes with compile/tests or targeted smoke checks when possible.
- Be careful with file-mode-only git diffs on Windows/WSL (known footgun).

---

## Python

- Target version: 3.13 (`.venv/pyvenv.cfg`).
- Type hints throughout, including modern union syntax (`str | None`) and `Mapped[...]` generics in SQLAlchemy models.
- Module-level docstrings are short, one-purpose-sentence style: `"""Database model for network sessions."""`. Class docstrings likewise one or two lines. No multi-paragraph docstrings observed.
- No repository-wide linter/formatter/type-checker config found (no ruff, black, flake8, mypy, isort) — style consistency is currently maintained by convention and review, not tooling. See `docs/environment.md` (Code Quality) for the Unknown-tooling caveat.

### Backend (FastAPI, `backend/`)

- Feature module layout, one per concern under `backend/app/features/<name>/`: `router.py`, `dependencies.py`, `service.py`, `repository.py`, `models.py`, `schemas.py`, `exceptions.py` (not every feature has all files — e.g. `threats/` has no `models.py`, reusing `alerts` models; see `docs/database.md`).
- Routers stay thin: `@router.get/post/...` handlers call into a service, no business logic or DB access inline. Router construction: `router = APIRouter(prefix="/<name>", tags=["<Tag>"])`.
- Raise app/feature exceptions in service/repository layers (subclasses of `AppException`, `app/common/exceptions.py` — `status_code` + `error_code` + `details` dict), not raw `HTTPException`. Central mapping to HTTP responses happens in `app/common/exception_handlers.py`.
- Every success response goes through `create_response(data, message, status_code)` (`app/common/responses.py`), producing `{ data, message, meta: { timestamp, request_id } }`. Don't hand-build response dicts in routers.
- Structured logging: `logger = logging.getLogger("app")`, with `exc_info=True` on caught exceptions and useful IDs (e.g. `threat_id=%s`) in log fields.
- SQLAlchemy models: `CUIDMixin` + `TimestampMixin` + `Base` (`app/db/base.py`) on every table; `__tablename__` explicit; multi-column indexes declared via `__table_args__ = (Index(...), UniqueConstraint(...))` with explicit names following the project's naming convention (`ix_<table>_<cols>`, `uq_<table>_<col>`).
- Pydantic v2 patterns: `model_validate`, `model_dump(mode="json")`, `ConfigDict` — not v1-style `.dict()`/`.parse_obj()`.
- Async SQLAlchemy session via the request-scoped dependency in `app/db/session.py`; rely on request-scoped commit/rollback rather than manual transaction management in routers.
- Migrations: filenames are timestamp-prefixed (`YYYYMMDD_NNN_description.py`) except two early ones using bare Alembic hashes (`2a839dcadf78_create_api_keys_table.py`) — prefer the timestamp-prefixed style for new migrations, matching the majority.

### Packet capture / runtime (`packet_capture/`, `traffic_engine/`, `feature_engine/`, `ml/`, `threat_detection/`, `response_engine/`)

- `LiveSniffer`'s packet callback must remain parse + enqueue only — no ML inference, DB writes, network calls, file I/O, or other blocking work (hard constraint, not a style preference — see `docs/decisions.md`).
- Feature extraction (`feature_engine/extractors/session_feature_extractor.py`) must return exactly `ml/features/schema.py::FEATURE_COLUMNS` — no extra or missing fields.
- Use the safe-stats helpers in `feature_engine/stats.py` for min/max/mean/std/variance/rate/IAT computation; return neutral `0` instead of NaN/infinity when a value can't be computed safely — never let NaN/inf reach a model.
- Protocol values are numeric everywhere: TCP=6, UDP=17, ICMP=1, UNKNOWN=0 — never a string protocol name in ML-facing code.
- Queue-based producer/consumer boundaries where packet throughput matters (`Queue` between `LiveSniffer` and `PacketProcessor`); don't introduce synchronous cross-thread calls in the capture path.
- Never duplicate `FEATURE_COLUMNS` — always import the canonical list from `ml/features/schema.py`.

---

## Frontend (`frontend/`, TypeScript/Next.js)

- TypeScript `strict: true` (`frontend/tsconfig.json`) — no implicit `any`.
- ESLint config: `eslint-config-next` (`core-web-vitals` + `typescript` rule sets), run via `bun run lint`.
- Package manager is `bun` — scripts invoke `bun --bun next ...`; don't introduce `npm`/`yarn` lockfiles alongside `bun.lock`.
- Backend client wrappers live under `frontend/src/lib/backend/*.ts` (one file per resource, e.g. `threats.ts`, `sessions.ts`, `blocked-ips.ts`); direct Drizzle queries live under `frontend/src/lib/db/queries/*.ts` and are being phased toward read-only use (`docs/decisions.md`).

---

## Testing

- Test runner: `unittest` (`python -m unittest discover tests`), not `pytest`, despite a `pytest.ini` existing (currently vestigial — see `docs/environment.md`).
- Layout: `tests/unit/{backend,core,ml}/`, `tests/integration/api/`; filenames `test_*.py`.
- ML tests assert against the canonical `FEATURE_COLUMNS` (schema drift/order/completeness guards) rather than hardcoding feature lists.
- Smoke scripts (`backend/smoke/*.py`) are explicitly disposable scaffolding per `backend/CHECKLIST.md` — don't treat them as permanent regression coverage; remove alongside their README references once replaced by real tests.

---

## Documentation

- Update only the documentation directly affected by a change (see `docs/development-workflow.md`).
- Feature-level implementation notes belong in `backend/CHECKLIST.md` (start/end of task, major-change log), not scattered inline comments describing history.
