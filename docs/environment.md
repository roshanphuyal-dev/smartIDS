Analyze the repository and generate `docs/environment.md`.

Purpose:
This document is the single source of truth for the project's development environment, tooling, and operational commands.

Base everything strictly on repository evidence.

Do not invent commands or versions.

If information is unavailable, explicitly state "Unknown".

Include the following sections:

# Development Environment

- Programming languages and required versions
- Package managers
- Runtime requirements
- Operating system assumptions (if any)

# Project Dependencies

For each major dependency include:

- Purpose
- Installation method
- Version requirements (if specified)

# Repository Setup

Document the complete setup process for a new developer, including:

- Dependency installation
- Environment variables
- Configuration files
- Secrets (describe required variables only, never include values)

# Development Commands

Document all available commands, grouped by purpose.

Examples include:

- install
- build
- run
- development server
- lint
- format
- type checking
- test
- coverage
- documentation generation

Include only commands actually supported by the repository.

# Docker

If Docker is used, document:

- compose files
- build commands
- startup commands
- shutdown commands
- reset commands

# Database

If applicable, document:

- database engine
- migrations
- migration commands
- seed commands
- reset commands
- backup/restore commands

# Cache / Queue

Document services such as:

- Redis
- RabbitMQ
- Kafka

Include startup and maintenance commands if present.

# Frontend

If applicable:

- package manager
- dev server
- production build
- preview
- environment variables

# Backend

If applicable:

- server startup
- hot reload
- worker processes
- background jobs

# Testing

Document:

- unit tests
- integration tests
- end-to-end tests
- coverage

# Code Quality

Document:

- formatter
- linter
- static analysis
- security scanning

# Common Development Tasks

Examples:

- start everything
- stop everything
- reset development environment
- rebuild dependencies
- regenerate generated code

Include only tasks supported by the repository.

# Troubleshooting

Document common repository-specific issues discovered from the repository and their solutions.

# Notes

- Keep explanations concise.
- Prefer tables where appropriate.
- Do not duplicate architecture or API documentation.
- Do not explain technologies.
- This document is a reference, not a tutorial.
- Infer only from repository evidence.
- If uncertain, explicitly mark the section as Unknown rather than guessing.
Analyze the repository and generate `docs/development-workflow.md`.

Purpose:
This document defines the standard engineering workflow for contributors working on this repository.

It should describe *how work is performed*, not how the project is implemented.

Base everything on repository evidence and the existing documentation.

Do not invent workflows.

If information is unavailable, explicitly state "Unknown".

Include the following sections.

# Development Lifecycle

Describe the recommended sequence for completing any development task.

Example stages:

- Understand the task
- Load required context
- Plan
- Implement
- Verify
- Update documentation
- Commit

Keep each stage concise.

---

# Context Loading

Document which resources should be used for different tasks.

Examples:

| Task | Load |
|------|------|
| Planning | roadmap.md |
| Architecture | architecture.md |
| API | api.md |
| Database | database.md |
| Coding conventions | coding-standards.md |
| Design rationale | decisions.md |
| Environment | environment.md |
| Code understanding | Graphify |

State that only the minimum required context should be loaded.

---

# Graphify Workflow

Document when Graphify should be used.

Include:

- graphify query
- graphify explain
- graphify path

State that Graphify should be preferred over repository-wide searching.

Document when to run:

graphify update .

Examples:

- after moving files
- after adding modules
- after deleting modules
- after major refactoring

Do not recommend running it after every small edit.

---

# Planning Rules

Document when planning is required.

Examples:

- architecture changes
- database schema changes
- multiple-file modifications
- dependency changes
- public API changes

State that implementation should wait for approval after presenting the plan.

Skip planning for localized tasks.

---

# Implementation Rules

Document repository implementation expectations.

Examples:

- follow existing patterns
- avoid speculative abstractions
- modify only relevant files
- keep changes minimal
- preserve backwards compatibility unless intentionally changing it

---

# Verification

Document what should be verified before considering work complete.

Include:

- tests
- lint
- formatting
- type checking
- manual verification
- API compatibility (when applicable)

Include only repository-supported verification methods.

---

# Documentation Maintenance

Document when each documentation file should be updated.

| Change | Update |
|---------|--------|
| Architecture | architecture.md |
| API | api.md |
| Database | database.md |
| Coding conventions | coding-standards.md |
| Roadmap | roadmap.md |
| Environment | environment.md |
| Design decisions | decisions.md |

State that unrelated documentation should not be modified.

---

# Git Workflow

If repository evidence exists, document:

- branch strategy
- commit conventions
- merge strategy
- release strategy

Otherwise state Unknown.

---

# Definition of Done

A task is complete only if applicable items are satisfied.

Include:

- implementation complete
- verification complete
- documentation updated
- Graphify updated after structural changes
- no unrelated modifications remain

---

# Principles

Keep the workflow:

- concise
- repository-specific
- deterministic
- easy to follow

Avoid philosophy, tutorials, or explanations of technologies.

Infer only from repository evidence.

If uncertain, explicitly state Unknown.
