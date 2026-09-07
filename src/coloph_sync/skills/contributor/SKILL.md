---
name: coloph-sync-contributor
description: Commit work in a repository managed by coloph-sync, handle failed checks, or repair an integration conflict.
---

Keep work in the assigned branch. Read the repository's check and deployment instructions.
The commit-msg hook owns check results. An ordinary commit needs no input marker.
Never copy a passed marker to avoid checks. The hook always checks ordinary commits.

For an intentional checkpoint, put `Sync-State: wip` on its own commit-body line.
For a checked scaffold, use `Sync-State: dont-merge`. It permits a later local merge but blocks integration at that tip.
For a deployment boundary, create an empty commit with `Sync-State: deploy-barrier` after the prerequisite commit.
Do not combine states. The subject describes the change without control prefixes.

A check exit of 1 saves a failed commit. Read its diagnostic, repair the work, and create another ordinary commit.
A rejected hook does not create a commit. Repair the stated error and retry.
Do not bypass the hook or rewrite check results.

Read `coloph-sync status`. A conflict belongs to the branch owner.
Follow the repository's merge procedure to integrate main and resolve the conflict.
Do not operate the coordinator while repairing your branch.
The coordinator attempts merges; it does not resolve conflicts or write repairs.
