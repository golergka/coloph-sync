# Working on coloph-sync

Keep this project simple. Use the smallest change that solves an established problem.
Keep issue management minimal. Keep design and implementation in the same feature issue.
Explain open choices in that issue. A feature is complete when it works, not when a plan exists.

Use plain English and concrete examples. Explain current behavior before introducing a proposed feature.
For bugs and small improvements, explain the actual result, expected result, and practical impact.
Do not present a proposed feature as a broken existing feature.
Do not create work merely because a test is missing.
Preserve useful issue text and keep revisions targeted.

Never publish links or references to private repositories in code, documentation, issues, pull requests, comments, or release notes.
Public explanations must stand alone without private project context.

Before a release, run `uv lock --check`, `uv run pytest -q`, `uv run ruff check .`, and `python scripts/release.py build --tag vX.Y.Z`.
Release tags must match the package version and are immutable.
Use `MAJOR.MINOR.PATCH` versions. Increase MAJOR for incompatible interfaces, configuration, state, or hook behavior.
Increase MINOR for backward-compatible features. Increase PATCH for backward-compatible fixes.
A version change requests a release. Ordinary commits keep the current version and do not publish a package.
The deployment command publishes the declared version. It only verifies `origin/main` when that version is already published.

Shadow mode and cross-machine handover, leases, and fencing were rejected.
Do not reintroduce them unless the user explicitly changes that decision.

Read README.md for the current CLI and project-command interfaces.
