# Development Workflow

Standard engineering workflow for contributors to SmartIDS. Describes how work is performed, not how the system is implemented (see `docs/architecture.md` for that).

---

## Development Lifecycle

| Stage | Description |
|-------|-------------|
| 1. Understand the task | Identify task type (bug fix, feature, refactor, docs, ML/dataset work). |
| 2. Load required context | Load only the documentation/tools needed for this task type (see Context Loading). |
| 3. Plan | Required for architecture/multi-file/public API/DB/dependency changes (see Planning Rules). Skip for localized work. |
| 4. Implement | Follow existing patterns; touch only relevant files (see Implementation Rules). |
| 5. Verify | Run applicable tests/smoke checks (see Verification). |
| 6. Update documentation | Update only docs directly affected by the change. |
| 7. Commit | Free-form descriptive commit message (see Git Workflow). |

---

## Context Loading

Load only the minimum required context for the task.

| Task | Load |
|------|------|
| Planning next work | `docs/roadmap.md` |
| System design | `docs/architecture.md` |
| API implementation | `docs/api.md` |
| Database changes | `docs/database.md` |
| Repository conventions | `docs/coding-standards.md` |
| Previous architectural decisions | `docs/decisions.md` |
| Environment/tooling | `docs/environment.md` |
| Code understanding | Graphify (`graphify-out/`) — present and populated. |

`AGENTS.md`, `backend/AGENTS.md`, `README.md`, `backend/README.md`, and `backend/CHECKLIST.md` remain useful supplementary sources — several roadmap/decision entries above were sourced from them, and `backend/CHECKLIST.md` is more granular/current than `docs/roadmap.md`'s snapshot. `backend/AGENTS.md` and root `AGENTS.md` also contain some stale statements now flagged in `docs/roadmap.md` — cross-check before trusting a claim from either against current code.

---

## Graphify Workflow

This repository has a populated `graphify-out/graph.json`. Prefer Graphify over repository-wide grep/search for code understanding.

- `graphify query "<question>"` — scoped subgraph for a question.
- `graphify explain "<concept>"` — explain a concept using the graph.
- `graphify path "<A>" "<B>"` — relationship path between two symbols/files.
- `graphify-out/wiki/index.md` — repository navigation entry point.
- `graphify-out/GRAPH_REPORT.md` — high-level architecture summary; read only when Graphify query/explain/path is insufficient.

Run `graphify update .` after:

- moving files
- adding modules
- deleting modules
- major refactors

Do not run it after every small edit.

---

## Planning Rules

Plan first and wait for approval before implementing when the task involves:

- architecture changes
- database schema changes
- multi-file modifications
- new or changed dependencies
- public API changes
- significant refactoring

A plan = current understanding summary + concise implementation plan, presented before code changes.

Skip planning for localized tasks: bug fixes, documentation updates, formatting, tests, or changes following an established pattern already in the codebase.

---

## Implementation Rules

Repository-observed conventions (from `AGENTS.md` and `backend/AGENTS.md`):

- Solve only the requested problem; avoid speculative abstractions.
- Match existing patterns; touch only files relevant to the task.
- Keep modules isolated by responsibility: capture, parsing, session/flow management, feature extraction, ML, alerting, response handling (`AGENTS.md`).
- Keep APIs/routers thin; business logic lives in services, DB access in repositories (`router -> dependencies -> service -> repository -> models/schemas`, per `backend/AGENTS.md`).
- Raise app/feature exceptions in service/repository layers, not raw `HTTPException`.
- Use structured logging (`logger = logging.getLogger("app")`) with useful IDs in log fields.
- Use the Pydantic v2 patterns already present (`model_validate`, `model_dump(mode="json")`, `ConfigDict`).
- `packet_capture` hot path: `LiveSniffer._handle_packet` stays minimal (parse + enqueue only) — no ML inference, DB writes, network calls, file I/O, or blocking work in the sniff callback.
- ML runtime contract: all dataset cleaning, training, evaluation, model saving, and live extraction must import the single canonical `ml/features/schema.py::FEATURE_COLUMNS`. Never duplicate feature lists across files.
- Preserve backward compatibility of the backend response envelope and existing auth/API-key route semantics unless a change is explicitly requested.
- After Python dependency changes, update the relevant requirements file (`requirements.txt` / `requirements_windows.txt` / `backend/requirements.txt`) from the active environment.

---

## Verification

| Check | Command | Notes |
|-------|---------|-------|
| Root/backend unit + integration tests | `.venv/bin/python -m unittest discover tests` (Linux) / `.\.venv_windows\Scripts\python.exe -m unittest discover tests` (Windows) | Test discovery root: `tests/`. |
| Focused test | `python -m unittest tests.unit.core.test_engine_telemetry` (example) | Substitute target module. |
| Backend smoke checks | e.g. `.venv/bin/python backend/smoke/smoke_database_barrel_import.py` | Temporary scaffolding per `backend/CHECKLIST.md`; remove once cutover is stable. |
| ML model train/evaluate | `.venv/bin/python -m ml.training.train_xgboost_cicids2018` then `.venv/bin/python -m ml.evaluation.evaluate_cicids2018` | No atomic build/verify/activate command yet for the CICIDS2018 path; copy artifacts into `ml/saved_models/CICIDS_XGBOOSTER` manually. |
| Frontend lint | `bun run lint` (in `frontend/`) | ESLint via `eslint`. |
| Frontend tests | Unknown | No `test` script defined in `frontend/package.json`. |
| Python lint/format/type-check | Unknown | No ruff/black/flake8/mypy config or dependency found in the repo. `pytest.ini` exists at root but README documents `unittest discover`, not `pytest`, as the test runner. |
| Backend migrations | `python script.py migrate upgrade` (from `backend/`) | Alembic-backed; see `backend/alembic.ini`. |

Manual/API-level verification: hit affected endpoints and, if touched, the websocket path (per `backend/AGENTS.md` Change Safety Checklist).

---

## Documentation Maintenance

| Change | Update |
|--------|--------|
| Architecture | `docs/architecture.md` |
| API | `docs/api.md` |
| Database | `docs/database.md` |
| Coding conventions | `docs/coding-standards.md` |
| Roadmap | `docs/roadmap.md` |
| Environment/tooling | `docs/environment.md` |
| Design decisions | `docs/decisions.md` |
| Backend implementation progress | `backend/CHECKLIST.md` — update at the start and end of each backend implementation task; record all major DB/model/API-contract/plan changes. |

Do not modify unrelated documentation.

---

## Git Workflow

Based on observed repository state only:

- **Branches**: two known — `main` (also `origin/HEAD`) and `ml` (current branch). No branch-naming convention or protection rules found in-repo. Formal branch strategy: Unknown.
- **Commits**: free-form, descriptive, present/past-tense sentences (e.g. "Retrained the model and added it", "Bug fix: adding persistance..."). No enforced Conventional Commits format observed in history, despite a `caveman-commit` skill being installed that can generate that style.
- **Submodules**: `backend` and `frontend` are git submodules (`.gitmodules`); commits that touch them often update the submodule pointer explicitly.
- **Merge strategy**: history on `ml` is linear with no merge commits visible — suggests fast-forward/rebase workflow, but insufficient evidence for a documented policy. Unknown.
- **CI**: no GitHub Actions workflow found under `.github/` (only `copilot-instructions.md`, an assistant style config, not a pipeline). Unknown.
- **Release strategy**: Unknown — no tags, changelog, or release docs found.

---

## Definition of Done

A task is complete only when applicable items are satisfied:

- [ ] Implementation solves only the requested problem; no unrelated files touched.
- [ ] Verification complete: relevant unit/integration tests and/or smoke checks pass; frontend lint passes if frontend touched.
- [ ] Documentation updated (only docs directly affected by the change).
- [ ] `graphify update .` run if files/modules were moved, added, deleted, or majorly refactored.
- [ ] `backend/CHECKLIST.md` updated if the change is a backend implementation task.
- [ ] No unrelated modifications remain in the diff.

---

## Principles

- Concise, repository-specific, deterministic.
- Derived from repository evidence (`AGENTS.md`, `backend/AGENTS.md`, `README.md`, `backend/README.md`, `backend/CHECKLIST.md`, `.gitmodules`, git history, installed tooling) and existing `CLAUDE.md` policy.
- Where evidence was insufficient, marked explicitly as Unknown rather than inferred.
