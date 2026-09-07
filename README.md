# coloph-sync

Commit checks, local worktree integration, and deployment coordination for any Git project.
The utility is written in Python. Projects integrate through commands, not Python imports.
Extracted from [Coloph](https://github.com/golergka/coloph), under GPL-3.0-only.

## Install and configure

Install from a release:

```sh
uv tool install git+https://github.com/golergka/coloph-sync@v0.1.0
```

Create `coloph-sync.toml` at the repository root:

```toml
main_ref = "main"
remote = "origin"
commit_check = ["./scripts/check", "commit"]
merge_check = ["./scripts/check", "merge"]
integration_check = ["./scripts/check", "integration"]
deploy_command = ["./scripts/deploy"]
```

Supply real executable check and deployment commands before installation.
Run `coloph-sync install-hooks`. Existing commit-msg hooks run before the managed hook; uninstall restores them.
Run `coloph-sync run --once` in the clean main checkout, or `coloph-sync run` for continuous operation.
Deployment is required. Remote branches and cloud supervision are outside this release.

Optional configuration: `preflight_command`, `deployed_ref` (default `deployed`), `deploy_tag_prefix` (default `deploy`),
`check_timeout` and `deploy_timeout` (14400 seconds), `merge_timeout` (1500 seconds), and `interval` (60 seconds).
Missing merge or integration commands use `commit_check`.
`coloph-sync.local.toml` overrides local configuration. Unknown keys fail. `--config PATH` selects another root.
Secrets belong in the command environment, not the checked-in configuration.

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
Exit 0 confirms the complete release of the exact target. Nonzero leaves the attempt unconfirmed and stops the loop.
Repeated calls with the same attempt ID and target must reconcile or resume safely, including remote work still running.
The command owns all infrastructure details. It must not publish the coordinator's deployment refs.

The engine persists completion before publishing an immutable `deploy/<attempt-id>` tag and the moving `deployed` tag.
Publication retries do not redeploy a completed attempt. Concurrent changes to the moving tag fail explicitly.
A lost success acknowledgment remains uncertain and requires reconciliation by the deployment command on retry.
An unfinished attempt is resolved before another integration cycle. Rollback is not automatic.
Manual deployment uses `coloph-sync deploy` and the same lock and records.
Explicit recovery uses `coloph-sync deploy --commit SHA --rollback`. The command receives `COLOPH_SYNC_ROLLBACK=1`.
The deployment command owns whether that recovery is safe. Normal runs never select rollback.

## Status and agents

```sh
coloph-sync status
coloph-sync --json status --commit <sha>
coloph-sync wait --commit <sha> --until deployed
coloph-sync stop
coloph-sync logs
coloph-sync skill contributor
coloph-sync skill operator
coloph-sync skill finish
```

Link repository agent instructions to these bundled skills. Keep project-specific checks and production smoke procedures in the project.
Stop drains the current cycle. SIGTERM also drains. A forced interruption cannot cancel remote deployment work reliably.
State and logs live in the shared Git directory, so linked worktrees see the same results.
The engine requires a POSIX host, Git, Python 3.12+, and the project's command dependencies.

## Development

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
```

The tests use disposable Git repositories and local remotes. They do not deploy real services.
