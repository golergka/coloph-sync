# coloph-sync

Commit checks, local worktree integration, and deployment coordination for any Git project.
The utility is written in Python. Projects integrate through commands, not Python imports.
Licensed under GPL-3.0-only.

## Install and configure

Add the CLI to the repository's development dependencies and commit the updated project file and lockfile:

```sh
uv add --dev 'coloph-sync==0.3.2'
uv run coloph-sync init
```

The CLI is implemented in Python, but host projects integrate through executable commands and can use any language.

`init` installs the four agent workflows under `.agents/skills/` and creates `coloph-sync.toml` if absent:

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
Saving work means creating a commit. A WIP or failed checkpoint is not finished work.
These rules remain mandatory if the agent host does not enforce working-directory boundaries mechanically.
The managed commit hook enforces commit states, not worktree ownership. Configure host work-directory and command guards when available.

Choose a project pattern and replace the example commands with real project commands. Document the project policy for agents.
Then run `uv run coloph-sync install-hooks`.
Existing commit-msg hooks run before the managed hook; uninstall restores them.
Contributors work only in their assigned linked worktrees. Reserve the clean `main` checkout for the assigned coordinator.
Codex discovers the workflows from `.agents/skills/`. Identical installed workflows are left alone. `init` stops before writing if an existing workflow differs; `install-skills` explicitly replaces stale workflow copies with the installed package versions.
Every other CLI command first compares these three small files with the installed package and exits with recovery instructions if they are missing or stale.
Run `uv run coloph-sync run --once` in the clean main checkout, or `uv run coloph-sync run` for continuous operation.
Use `run --branch NAME` to restrict integration to one local worktree branch.
Use `run --push-deploy-only` to skip branch merges, run the integration check, push main, and deploy it.
A delivery command is required. Remote branches and cloud supervision are outside this release.

## Usage patterns

Different projects can use the same sync loop with different delivery policies.
Coloph-sync coordinates the loop. The project commands define what a successful check and delivery mean.

This repository is a versioned-package example. It uses deliberate semantic versions and does not publish every commit.
Its deployment command publishes only when `pyproject.toml` contains a new version.
For other commits, the command verifies `origin/main` and the existing package release.

A continuously deployed web app can deploy every integrated commit instead.
The [example project](example/README.md) shows this pattern with a deployment command that waits for a hosting service.
The service must report the exact commit as live before the command succeeds.

Coloph-sync owns these tasks:

- Run the project commands at the configured stages.
- Integrate eligible local worktree branches into the main branch.
- Push the main branch and coordinate one delivery attempt at a time.
- Record results and publish its coordination tags.

The project owner supplies these parts:

- Checks for commits, merges, and the integrated main branch.
- The release or deployment policy.
- An idempotent deployment command that reconciles retries.
- Credentials, infrastructure access, and the definition of delivery success.

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

The engine discovers local worktrees, sorts their branches, and attempts ordinary Git merges.
It skips blocked tips and isolates merge conflicts. Metadata failures retry after the branch changes.
Conflicts retry after either the branch or target changes. Timeouts retry on the next cycle.
At a deployment barrier, only its parent can merge until that parent has completed deployment.

## Deploy contract

The command receives `COLOPH_SYNC_COMMIT`, `COLOPH_SYNC_ATTEMPT_ID`, `COLOPH_SYNC_RUN_ID`,
`COLOPH_SYNC_DEPLOYED_COMMIT`, and `COLOPH_SYNC_CONTEXT=deploy`.
Exit 0 confirms the project-defined delivery of the exact target. Nonzero leaves the attempt unconfirmed and stops the loop.
Repeated calls with the same attempt ID and target must reconcile or resume safely, including remote work still running.
The command owns all infrastructure details. It must not publish the coordinator's deployment refs.

For a versioned package, delivery does not have to publish every commit. This repository demonstrates that pattern.
The project can use a version change as its release request.
The command publishes only a new declared version. If the version is unchanged, the command can complete without publication.
The project owns its version policy and registry checks. Coloph-sync does not select or increase versions.

A verification-only command is also valid. It can confirm that the target reached the required Git branch and then exit 0.
In this configuration, `deployed` means that the project-defined verification completed. It does not mean that an artifact was published.

The engine persists completion before publishing an immutable `deploy/<attempt-id>` tag and the moving `deployed` tag.
Publication retries do not redeploy a completed attempt. Concurrent changes to the moving tag fail explicitly.
A lost success acknowledgment remains uncertain and requires reconciliation by the deployment command on retry.
An unfinished attempt is resolved before another integration cycle. Rollback is not automatic.
Manual deployment uses `uv run coloph-sync deploy` and the same lock and records.
Explicit recovery uses `uv run coloph-sync deploy --commit SHA --rollback`. The command receives `COLOPH_SYNC_ROLLBACK=1`.
The deployment command owns whether that recovery is safe. Normal runs never select rollback.

## Status and agents

```sh
uv run coloph-sync status
uv run coloph-sync --json status
uv run coloph-sync stop
uv run coloph-sync logs
uv run coloph-sync init
uv run coloph-sync install-skills
uv run coloph-sync skill contributor
uv run coloph-sync skill merge-main
uv run coloph-sync skill operator
uv run coloph-sync skill finish
```

The installed skill descriptions tell agents when to use contributor, merge-main, operator, and finish workflows.
Their installed names are `sync-contributor`, `sync-merge-main`, `sync-operator`, and `sync-finish`.
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
