# SmartIDS

## Purpose

This file contains repository-specific instructions for SmartIDS.

Global behavioral rules are defined in the user's global CLAUDE.md.

---

## Repository Documentation

Load documentation only when required.

| Task | Document |
|------|----------|
| Planning next work | docs/roadmap.md |
| Understanding system design | docs/architecture.md |
| API implementation | docs/api.md |
| Database changes | docs/database.md |
| Repository conventions | docs/coding-standards.md |
| Previous architectural decisions | docs/decisions.md |

Never preload unrelated documentation.

---

## Graphify

This repository uses Graphify.

For code understanding:

1. Prefer Graphify before repository-wide searching.
2. Use:
   - `graphify query "<question>"`
   - `graphify explain "<concept>"`
   - `graphify path "<A>" "<B>"`
3. Use `graphify-out/wiki/index.md` for repository navigation.
4. Read `graphify-out/GRAPH_REPORT.md` only for high-level architecture or when Graphify cannot provide sufficient context.

After structural code changes run:

```bash
graphify update .
```

---

## Repository Workflow

For every task:

1. Determine the task type.
2. Load only the required documentation.
3. Use Graphify when understanding existing code.
4. Read source files only when necessary.
5. Implement.
6. Verify.
7. Update only documentation affected by the change.

---

## Repository Constraints

Infer these from the repository:

- Build commands
- Test commands
- Development commands
- Package manager
- Required language versions
- Docker workflow
- Migration workflow
- Generated code
- Protected files/directories

If repository evidence is insufficient, ask instead of assuming.

---

## Repository Notes

- Do not invent architecture.
- Do not invent roadmap items.
- Do not invent coding conventions.
- Do not infer business goals from implementation alone.

Use repository evidence before making conclusions.
