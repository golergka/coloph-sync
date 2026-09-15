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
Use `run --push-deploy-only` to resolve pending delivery, skip branch merges, check main, push it, and deploy it.
After a deployment command fails because its checked-in implementation is broken, put the repair on one checked
contributor branch. From the stopped coordinator checkout, run
`uv run coloph-sync run --once --branch NAME`. This merges and checks only that branch,
resolves the outstanding deployment, then pushes and deploys the repair commit as a new attempt.
For a checked repair already on main, use `uv run coloph-sync run --once`.
The older `--repair-pending-deploy` option remains available for compatibility. Normal operation does not require it.
A repository adopted after feature work has begun can merge its active worktree branches with `uv run coloph-sync adopt --all`.
It runs the normal merge check for each branch, preserves its existing commits, and records each successful adoption in the shared Git directory.
Branches that conflict or fail their merge check remain unadopted; later commits still require valid `Sync-State` metadata.
A delivery command is required. Remote branches and cloud supervision are outside this release.

Optional configuration: `preflight_command`, `reconcile_command`, `deployed_ref` (default `deployed`), `deploy_tag_prefix` (default `deploy`),
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

The command receives `COLOPH_SYNC_COMMIT`, `COLOPH_SYNC_ATTEMPT_ID`, `COLOPH_SYNC_RUN_ID`,
`COLOPH_SYNC_DEPLOYED_COMMIT`, and `COLOPH_SYNC_CONTEXT=deploy`.
Exit 0 confirms the project-defined delivery of the exact target. Nonzero leaves the attempt unconfirmed and stops the loop.
Repeated calls with the same attempt ID and target must reconcile or resume safely, including remote work still running.
The command owns all infrastructure details. It must not publish the coordinator's deployment refs.

For a versioned package, delivery does not have to publish every commit. This repository demonstrates that pattern.
The project can use a version change as its release request or calculate a version automatically from each eligible commit.
The command publishes only a new declared version. If the version is unchanged, the command can complete without publication.
The project owns its version policy and registry checks. Coloph-sync does not select or increase versions.

A verification-only command is also valid. It can confirm that the target reached the required Git branch and then exit 0.
In this configuration, `deployed` means that the project-defined verification completed. It does not mean that an artifact was published.

The engine persists completion before publishing an immutable `deploy/<attempt-id>` tag and the moving `deployed` tag.
Publication retries do not redeploy a completed attempt. Concurrent changes to the moving tag fail explicitly.
A lost success acknowledgment remains uncertain and requires reconciliation by the deployment command on retry.
An outstanding attempt is resolved before another delivery. A selected checked repair can merge before that resolution.
Rollback is not automatic.
Manual deployment uses `uv run coloph-sync deploy` and the same lock and records.
Explicit recovery uses `uv run coloph-sync deploy --commit SHA --rollback`. The command receives `COLOPH_SYNC_ROLLBACK=1`.
The deployment command owns whether that recovery is safe. Normal runs never select rollback.

### Recovery evidence

The deployment command can run from a newer checked checkout during recovery.
It must use `COLOPH_SYNC_COMMIT` for payload contents and version selection, not the checkout contents.
Repaired tooling can change how delivery works without changing the requested payload.
An unchanged retry must reconcile external work before it repeats an irreversible action.

Projects can configure `reconcile_command` for automatic recovery decisions.
It receives the deployment environment with `COLOPH_SYNC_CONTEXT=reconcile`.
It must inspect external state without starting another deployment.
Its output contains exactly one JSON object, for example:

```json
{"outcome": "replace", "reason": "The workflow ended before publication; the registry contains no artifacts."}
```

- `delivered`: evidence confirms delivery of the exact target. The coordinator records success without another deployment.
- `retry`: the deployment command can safely resume the same target and attempt.
- `replace`: the old operation is terminal, and evidence proves that a successor is safe.
- `blocked`: the reason identifies missing evidence or a required repair. The coordinator stops without changing delivery records to success.

A nonzero exit, invalid output, or unknown outcome stops recovery. Every outcome requires a nonempty reason.
Replacement requires a checked descendant on main and cannot cross an undelivered deployment barrier.
The coordinator preserves the old attempt and evidence in delivery history without marking it deployed.
The project command owns evidence about partial publication, active remote jobs, and external effects.
The coordinator never infers safe replacement from a failed command or timeout alone.

Without `reconcile_command`, the coordinator retries the original deployment command with the original target and attempt.
Completed deployments only retry coordinator refs. They never run reconciliation or deployment again.

### Project command lessons

Local checks and CI use the same validation command. New releases also build and exercise their artifacts before tag creation.
Tags and artifacts refer to the checked source. Existing immutable contents are checked, never overwritten.
Network failures can occur after validation. Project commands therefore handle existing releases and partial success explicitly.
Branch delivery and package publication remain separate facts under project policy.

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
