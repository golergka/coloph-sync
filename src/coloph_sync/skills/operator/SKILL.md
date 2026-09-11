---
name: sync-operator
description: Operate and supervise the sync coordinator in its assigned integration checkout. Recover failed cycles without taking contributor work.
---

# Sync Operator

Operate only in the checkout assigned to the coordinator. Contributors use `sync-finish` for their branches.

The coordinator owns the integration checkout, its shared lock, automatic merges, checks, pushes, and delivery attempts. Do not start an independent deployment.

## Start and supervise

Before you start, check the assigned checkout, configured main branch, clean tree, project prerequisites, and existing coordinator instance.

Start or resume continuous operation unless the user asks for inspection, stopping, or one cycle. Run `uv run coloph-sync run` in the foreground. Keep the terminal or service identity that owns the process.

For detached operation, use the project's launcher or a terminal multiplexer. Use the host sleep-prevention mechanism when required. Do not duplicate an existing sleep assertion.

Before you end a turn with continuous operation active, create or reuse one recurring operator reminder for this task and checkout. The reminder must load this skill, check the owned process, run `uv run coloph-sync status --all` and `uv run coloph-sync logs`, and report only a state change or actionable failure.

## Stop and recover

Use `uv run coloph-sync stop` to drain the current cycle. Delete the operator reminder. Wait for the owned process to exit before you report that it stopped.

Do not edit files or run mutating Git commands while the coordinator owns the checkout.

A failed cycle exits. Read `uv run coloph-sync logs` and `uv run coloph-sync status --all`. Report deployment failures. Never skip checks. A nonzero deployment result does not prove that remote state is unchanged.

Branch conflicts, blocked tips, and invalid metadata belong to their branch owners. Tell the owner to use `sync-merge-main` for a conflict. Do not resolve contributor conflicts in the integration checkout.

For an authorized repair in this checkout, stop the coordinator, use `sync-contributor`, create a passed repair commit, then resume the coordinator. Without that authorization, report the required contributor work.

Use `uv run coloph-sync run --once` for recovery. Use `uv run coloph-sync run --push-deploy-only` only to check and deliver the current integration branch without admitting contributor branches.

The coordinator reconciles an unfinished delivery before it admits new work. Do not move deployment tags manually. Do not start a second deployment. Do not run an automatic rollback.

After three failed repairs for the same cause, report the blocker and stop automatic retries. Remove the reminder when the coordinator needs unavailable input or new authority.

## Branch and release rules

An empty `Sync-State: deploy-barrier` delays successors until its parent is delivered. A failed pre-barrier merge needs a repair before the barrier. Do not bypass a barrier.

The project owns check commands, deployment procedures, infrastructure recovery, and release policy. Use those instructions for check or delivery failures. Do not substitute weaker checks or a second release path.
