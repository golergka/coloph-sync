# Working on the continuous web app

Work only in the current worktree and branch. Never inspect another worktree or the integration checkout.
Do not create another worktree or switch branches unless the user explicitly requests that operation.
If the assigned worktree is detached, create a descriptive `codex/` branch at its current HEAD.
Saving work means creating a commit. A WIP or failed checkpoint is not shipped work.
Reserve the clean `main` checkout for the assigned sync coordinator.

Run `./scripts/check` before you ship work.
Each integrated commit deploys automatically. This project does not use release versions.
After delivery, serve `$WEB_ROOT/current` and confirm that the changed page works in a browser.
