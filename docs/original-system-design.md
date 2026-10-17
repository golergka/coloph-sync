# Coloph-ship: original system design

This document describes the system as a whole, including earlier implementations and project-specific extensions. It is a design reference, not a specification of the current coloph-sync release. Some components described here are not present in the current package.

The goal: get agents' changes into production. For the current package contract, see the [README](../README.md).

## Goal

Solve the merge and release problem for many parallel coding agents working on different tasks.

## Main principle

**Ship loop.** Ready branches are merged one by one in a loop. Unsuccessful merges or checks go back to the agents responsible for them. After a pass, the combined main branch is checked, pushed and delivered when delivery is required. Delivery usually means deploying to staging, but the project defines what it means.

## Components

- **Contributor coding agent:** owns a Git worktree and a branch, implements changes. Responsible for getting its changes correct and mergeable, then validating the delivered feature.
- **Automatic verification:** programmatic correctness checks, usually type checking, linting and tests. The project defines separate commit, merge and integration commands; merge and integration checks default to the commit command when not specified.
- **Code review:** performed automatically on ordinary commits by a tree of agents. They receive the changeset and relevant history and produce structured findings, mapped to a pass or fail decision. This is a project integration, not a reviewer built into the public sync library.
- **Deploy adapter:** a project-defined command that delivers the exact assembled commit. It may deploy an application, publish a requested release or only verify that the commit reached the required upstream branch.
- **Coordinator:** the programmatic main-loop controller. It owns integration and delivery. An operator agent diagnoses shared failures and arranges repairs; contributor agents resolve their own branch conflicts.

## Workflow

A contributor works on one piece of work according to the project's instructions. Its goal is to get that work delivered and tested, not just committed.

Intermediate progress can be saved in commits marked `Sync-State: wip`. These skip the managed verification command and are not picked up for integration. An ordinary commit triggers the project's checks and review. The hook writes the resulting state; the contributor cannot simply label unchecked work as passed.

In the project-specific review integration, a completed negative review saves a `failed` checkpoint. A deterministic-check failure or reviewer execution error rejects the commit instead. Either way, the contributor fixes the problem and makes another ordinary commit. Once it passes, the contributor follows its integration and delivery status.

The sync loop discovers local worktrees and processes their branches in sorted order. It skips dirty worktrees and blocked tips. Each eligible branch is merged into main and checked. If an automatic merge conflicts or receives a negative check result, that merge is aborted and the failure recorded. Other branches can continue. In the current public library, the coordinator does not resolve conflicts or write repairs; the earlier agent-controlled variant is described below.

The original contributor reads both histories from their shared merge-base, merges **local main** into its own branch, and resolves the conflict by preserving both changes' intent. It runs the required checks and leaves a checked tip for the next loop. The project-specific review integration runs deterministic checks on merge commits but skips LLM review; ordinary commits run both.

After the branch pass, the coordinator checks the combined tree, pushes main, and invokes the deploy adapter if needed. A passing branch is not proof that its combination with other branches passes. A successful merge is not proof of delivery.

### What `dont-merge` is for

`dont-merge` is a **checked scaffold**, not an unchecked WIP commit and not a permanent exclusion of the branch.

A contributor may need current main before its branch can pass, but merging from a `wip` or `failed` tip is prohibited. It first creates a reviewed scaffold marked `Sync-State: dont-merge`. That permits a subsequent local merge while preventing the coordinator from integrating the scaffold itself.

One project integration uses this for migration alignment: the scaffold has a narrow alignment exemption, while other checks and review still run. The later merge must pass alignment. The scaffold must pass its configured checks: a negative verdict changes it to `failed`. After main is integrated and the branch is fixed, a passing tip can be picked up normally, including the earlier scaffold in its history. The exclusion applies to the tip, not every descendant containing that commit.

### Deployment records and retries

The deploy command receives the exact commit, attempt ID, run ID and previous deployed commit. Release/version policy belongs to the project: automatic patch increments are possible project behavior, not a library guarantee.

The coordinator persists an attempt with its commit and state, progressing from `running` to `completed` to `published`. State files use atomic replacement and fsync. After the command confirms delivery, completion is saved **before** publishing two Git tags:

- `deploy/<attempt-id>`: an immutable record of that delivery attempt.
- `deployed`: a moving pointer to the delivered commit.

If delivery succeeded but publishing the tags failed, recovery publishes the records without deploying again. A concurrent change to the moving tag stops recovery for reconciliation. Retrying an unfinished attempt for the same commit reuses its identity.

A lost command acknowledgment does not prove deployment failed. The project adapter must inspect the external service and handle repeated calls safely. The sync library cannot guarantee exactly-once effects in arbitrary external systems.

An empty `deploy-barrier` commit separates dependent stages. Its parent must be delivered before subsequent changes integrate. For example, stop using a database column before dropping it. A repair needed to deliver the prerequisite belongs before the barrier, not behind it.

## Tools and harness

The workflow is supported by commands and agent instructions rather than relying on an agent to remember every step.

- `uv run coloph-sync run`: continuous coordinator loop; `--once` runs one cycle. `--branch NAME` selects one branch; `--push-deploy-only` skips branch integration.
- `uv run coloph-sync status`, optionally with global `--json`: reports branch/commit, merged/deployed state, checks, current phase and failure reason. An old failure is not applied to a newer, unprocessed branch tip.
- `uv run coloph-sync logs`: exposes diagnostics. State and logs live in the shared Git directory, so linked worktrees see the same results without committing operational files.
- `uv run coloph-sync stop`: drains the current cycle. It does not promise to cancel a remote deployment already started.
- `uv run coloph-sync deploy`: explicit delivery using the same lock and records, including an explicit rollback mode.
- Contributor, merge-main, operator, ship and release skills: instructions for implementation, semantic conflict repair, shared recovery, delivery validation and project release policy.

The current ship workflow checks status through scheduled waits and resumes repairs when needed. Earlier versions also provided a blocking status mode: the contributor could wait inside the tool call until processing completed or a failure required action.

An earlier coordinator implementation could resolve merge conflicts itself. This differs from the current public library, which aborts conflicted merges and leaves repair to the contributor. These earlier behaviors are confirmed by the author; their source revisions have not yet been pinned in this document. The current public loop does not launch an operator agent itself; the agent host supplies that supervision.

### Finish-work: decide whether the task is actually done

The finish-work skill carries responsibility beyond a successful commit or deployment. It specifically targets checks in the **deployed environment**, exercises the changed behavior, checks follow-ups and related work, and explains the current status to the developer.

Its final question is whether this piece of work is ready to close. A merged branch, a green check suite or a healthy service is not enough on its own. The agent should establish what was delivered, what was verified in the deployed environment, and whether unfinished follow-ups or related work prevent closure. If verification is unavailable or work remains, it must say so rather than report completion.

This describes the author's finish-work workflow. The current public package's closest counterpart is `sync-ship`, which explicitly requires delivered-behavior validation and follows the project's issue-closeout rules; the broader follow-up review should not be attributed to the sync engine itself.

## Hierarchical review

Review agents are split by concerns. In the hierarchical review implementation these include migration safety, database connection scoping, serialization, exception handling, timeouts, ownership boundaries and documentation consistency. Other projects can define different reviewers, such as design or schema-normalization specialists.

The root reviewer identifies concrete risks in the changeset, delegates focused questions and relevant hunks to the appropriate specialists, waits for them, and assembles their feedback. Reviewers have read-only tools. Python validates the structured output: no issues means pass; any issue means fail. Invalid output or a runtime failure is an infrastructure error, not an approval.

Review covers the staged changes plus the contiguous WIP/failed history since the review anchor. When a contributor fixes a failed review, the reviewer sees the cumulative changes and previous failed findings, oldest first. This reduces the chance of alternating between contradictory fixes or forgetting an unresolved objection; it does not guarantee the model will never oscillate.

The current implementation uses a **fresh session for each review**, including fixes. Previous findings are passed explicitly rather than relying on a preserved conversation. The root uses Sonnet and the concern specialists use Haiku. Mechanical invariants remain deterministic checks rather than prompt-only rules.

## Sources and scope

This is a design reference spanning multiple implementations, not an assertion that every component is present or active in the current release. The current public command contracts were checked against source; tests were not rerun for this document.

- [coloph-sync README and command contracts](../README.md)
- [Contributor workflow](../.agents/skills/sync-contributor/SKILL.md)
- [Merge-main workflow and checked scaffolds](../.agents/skills/sync-merge-main/SKILL.md)
- [Shipping and validation workflow](../.agents/skills/sync-ship/SKILL.md)
- [April coding-setup article](https://x.com/GolerGkA/article/2041734638444454267)

Earlier coordinator conflict resolution, blocking status and the broader finish-work workflow are included as part of the original system design. They should not be inferred to be features of the current CLI.
