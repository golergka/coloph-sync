# coloph-sync

Commit checks, local worktree integration, and deployment coordination for any Git project.
The utility is written in Python. Projects integrate through commands, not Python imports.
Licensed under GPL-3.0-only.

## Principles

1. **Work independently; coordinate shared changes.** Contributors own their work. One coordinator integrates, checks, and delivers shared changes.
2. **Projects define success; coloph-sync provides the machinery.** Checks, release policy, and delivery meaning belong to the project.
3. **Automate rules; use judgment for unresolved choices.** Scripts enforce mechanical rules. Agents interpret intent, diagnose failures, and repair code.
4. **Claims must follow evidence.** Checks, versions, and delivery records describe the actual work they refer to. Changed work needs fresh evidence.
5. **Interruption must not change correctness.** Retries preserve completed results and account for uncertain effects.
6. **Failure must have a path back to progress.** Isolate failures and preserve useful work. Permit checked repairs and safe replacements without false success.

## Install and configure

Add the CLI to the repository's development dependencies and commit the updated project file and lockfile:

```sh
uv add --dev coloph-sync
uv run coloph-sync init
```

In a Git repository without a version-controlled hook directory, `init` creates the project files and exits with the command needed to authorize hook setup. Run it once:

```sh
uv run coloph-sync init --install-hooks
git add .githooks/commit-msg
```

The option sets the repository-local `core.hooksPath` to `.githooks` and creates the managed hook there. Commit the hook with the other project files. Every linked worktree then receives it through checkout and needs no setup command.
If `core.hooksPath` already points inside the project, plain `init` installs the hook there without changing Git configuration.
If the generated hook is untracked and ignored, `init` identifies the matching ignore rule and warns that new worktrees will not receive the hook until it is unignored and committed.

The CLI is implemented in Python, but host projects integrate through executable commands and can use any language.

Add this instruction to the host project's `AGENTS.md`:

> After installing dependencies, run `uv run coloph-install-skills` to install or update skills bundled with installed packages.

`init` creates this configuration:

```toml
main_ref = "main"
remote = "origin"
commit_check = ["./scripts/check", "commit"]
merge_check = ["./scripts/check", "merge"]
integration_check = ["./scripts/check", "integration"]
deploy_command = ["./scripts/deploy"]
```

The user or agent host must create each worktree and assign it to one agent. Coloph-sync does not create, assign, or transfer worktrees.
An agent must remain in its assigned worktree. It must not create another worktree, switch branches, or inspect another worktree without explicit user authorization.
Approval for one worktree does not grant access to another worktree.
If an assigned worktree is detached, the agent creates a branch at its current HEAD. This is the only automatic branch operation.
Saving work means creating a commit. A WIP or failed checkpoint is not shipped work.
These rules remain mandatory if the agent host does not enforce working-directory boundaries mechanically.
The managed commit hook enforces commit states, not worktree ownership. Configure host work-directory and command guards when available.

Choose a project pattern and replace the example commands with real project commands. Document the project policy for agents.
Coloph-sync runs commit checks. If the project already uses pre-commit hooks for those checks, remove them and add their commands to `commit_check` in `coloph-sync.toml`.
Existing commit-msg hooks run before the managed hook; uninstall restores them.
Contributors work only in their assigned linked worktrees. Reserve the clean `main` checkout for the assigned coordinator.
Codex discovers the installed workflows from `.agents/skills/`.
Run `uv run coloph-sync run --once` in the clean main checkout, or `uv run coloph-sync run` for continuous operation.
Use `run --branch NAME` to restrict integration to one local worktree branch.
Use `run --push-deploy-only` to check, push, and deploy HEAD without branch merges.
After a failure, the operator diagnoses the cause and commits the repair.
The next `uv run coloph-sync run --once` cycle merges ready work, checks it, pushes main, and deploys HEAD.
Use `--branch NAME` to select one repair branch.
The coordinator reloads project commands after merges.
A repository adopted after feature work has begun can merge its active worktree branches with `uv run coloph-sync adopt --all`.
It runs the normal merge check for each branch, preserves its existing commits, and records each successful adoption in the shared Git directory.
Branches that conflict or fail their merge check remain unadopted; later commits still require valid `Sync-State` metadata.
A delivery command is required. Remote branches and cloud supervision are outside this release.

Optional configuration: `preflight_command`, `deployed_ref` (default `deployed`), `deploy_tag_prefix` (default `deploy`),
`check_timeout` and `deploy_timeout` (14400 seconds), `merge_timeout` (1500 seconds), `interval` (60 seconds), and
`live_output_limit` (65536 characters). When a project command exceeds `live_output_limit`, coloph-sync continues to
write its complete output to the run log, prints the log path once, and prints the final 4096 characters when it ends.
Missing merge or integration commands use `commit_check`.
`coloph-sync.local.toml` overrides local configuration. Unknown keys fail. `--config PATH` selects another root.
Secrets belong in the command environment, not the checked-in configuration.

## Project patterns and ownership

Coloph-sync owns commit states, local worktree integration, combined checks, retries, and delivery records.
The host project owns its checks, delivery meaning, infrastructure, version policy, agent policy, and manual validation.
The user or agent host owns worktree creation and assignment.

These patterns are all valid:

- Continuous delivery: each integrated commit updates a running application. See the [continuous web app example](example/continuous-web-app/README.md).
- Deliberate releases: ordinary commits only confirm integration. A project-defined change requests a versioned release.
- Verification only: the delivery command confirms that the commit reached a required branch or upstream. It publishes nothing.

This repository is the deliberate-release example. Its [configuration](coloph-sync.toml) uses project-owned check and delivery commands.
Its [agent instructions](AGENTS.md) define SemVer choices. A version increase requests a GitHub and PyPI release.
An unchanged version only confirms that the exact commit reached `origin/main`.

## Check contract

Commands receive the repository root as their working directory.
Hook commands receive `COLOPH_SYNC_CONTEXT` (`commit` or `merge`), `COLOPH_SYNC_MESSAGE` (absolute message path),
and `COLOPH_SYNC_REQUESTED_STATE`. They can append project reports to the message.
Exit 0 means passed. Exit 1 permits a failed checkpoint. Exit 2 rejects the commit.
Other exit codes and timeouts reject the commit. Stdout and stderr become diagnostic output.
An automatic merge with a negative verdict is aborted, not committed on main.
Integration and preflight commands require exit 0; any other result stops the cycle.

Exactly one standalone `Sync-State:` line appears in a completed commit body:
`wip`, `passed`, `failed`, `dont-merge`, or `deploy-barrier`.
The hook produces results; authors can request a WIP checkpoint, checked scaffold, or empty deployment barrier.
WIP and failed tips cannot be used as the starting point of a merge.
A checked scaffold permits a subsequent merge but cannot be integrated at that tip.
Older failed checkpoints do not block a later passed tip. All incoming commits must carry valid state metadata.
Fast-forward merges retain the original commit and its state; the integration check still checks the combined checkout.
`adopt` is the sole exception for legacy branches: it makes a checked merge commit after the normal merge check succeeds, preserving the older commit hashes.

The engine discovers local worktrees, sorts their branches, and attempts ordinary Git merges.
It skips a branch while its linked worktree is dirty and reports `worktree is dirty`; clean the worktree before the next cycle.
It skips blocked tips and isolates merge conflicts. Metadata failures retry after the branch changes.
Conflicts retry after either the branch or target changes. Timeouts retry on the next cycle.
At a deployment barrier, only its parent can merge until that parent has completed deployment.

## Deploy contract

Each cycle merges ready work, runs the integration check, pushes main, and deploys HEAD.
Deployment tooling, configuration, and payload all come from that commit.
The command receives `COLOPH_SYNC_COMMIT`, `COLOPH_SYNC_ATTEMPT_ID`, `COLOPH_SYNC_RUN_ID`,
`COLOPH_SYNC_DEPLOYED_COMMIT`, and `COLOPH_SYNC_CONTEXT=deploy`.

Exit 0 confirms project-defined delivery. A failure or interruption stops the cycle.
The operator diagnoses the failure and arranges a checked repair. The next cycle uses the same normal workflow.
Project commands own external operations and any necessary recovery.
A synchronous command can finish all its work before returning.
A command that starts background work checks that work through the relevant service before it reports delivery.

The project defines release policy. It can publish automatically, publish after a version change, or verify that HEAD reached a branch.
This repository publishes new declared versions. An already published version makes delivery verify that HEAD reached `origin/main`.
Project status therefore distinguishes branch delivery from package publication.

The coordinator saves completion before publishing its immutable attempt tag and moving `deployed` tag.
For a completed delivery, a repeated cycle can finish publishing those records.
Concurrent changes to the moving tag produce an error for operator review.
Manual deployment uses `uv run coloph-sync deploy` with the same lock and records.
An explicit `--commit` identifies HEAD. The `--rollback` option authorizes delivery of an intentionally restored HEAD.

Local checks and CI use the same validation command. New releases also build and exercise their artifacts before tag creation.
Tags and artifacts refer to the checked source. Project commands check existing publications through the registry.

## Status and agents

```sh
uv run coloph-sync status
uv run coloph-sync --json status
uv run coloph-sync stop
uv run coloph-sync logs
uv run coloph-sync init
uv run coloph-sync adopt --all
uv run coloph-sync skill contributor
uv run coloph-sync skill merge-main
uv run coloph-sync skill operator
uv run coloph-sync skill ship
```

The installed skill descriptions tell agents when to use contributor, merge-main, operator, ship, and release workflows.
Their installed names are `sync-contributor`, `sync-merge-main`, `sync-operator`, `sync-ship`, and `sync-release`.
Keep project-specific checks, delivery implementation, reviewers, and manual validation procedures in the project.
Stop drains the current cycle. SIGTERM also drains. A forced interruption cannot cancel remote deployment work reliably.
State and logs live in the shared Git directory, so linked worktrees see the same results.
The engine requires a POSIX host, Git, Python 3.12+, and the project's command dependencies.

## Development

GitHub releases test and build the matching tag, then publish its wheel and source distribution to PyPI.
This repository uses coloph-sync from its development environment. Its configuration and installed agent workflows are committed.
Ordinary commits only verify `origin/main`. A version increase makes the deployment command create and verify a PyPI release.

### Public writing

Read [AGENTS.md](AGENTS.md) for public writing and issue scope rules.

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
```

The tests use disposable Git repositories and local remotes. They do not deploy real services.
The [recovery exercises](example/recovery-lab/README.md) create separate projects with deliberate failures for agent evaluation.
