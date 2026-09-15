---
name: sync-release
description: Carry out a project-defined versioned release through the coordinator, with automatic or deliberate version policy.
---

# Release through the coordinator

Read the project release policy. The project owns version selection, release triggers, and publication checks.
Some projects release every eligible commit. Others use a deliberate version change.
Do not add manual version approval to an automatic release policy.

Use the assigned main checkout. Stop its coordinator and wait for exit before release edits.
Delete its operator reminder during deliberate release preparation.
Use `sync-operator` for supervision and shared failures.

For deliberate releases, review changes since the last published version and apply the project compatibility rules.
Check the declared version, existing tags, and published versions before proposing a version.
If the user authorized only inspection or preparation, report the proposal without publishing.
If release authorization and policy already determine the next action, proceed without asking again.
Ask only when compatibility or intended scope remains ambiguous.

Make the required version change and run the project release checks and build.
Create a checked commit. Then run:

```sh
uv run coloph-sync run --push-deploy-only
```

This command checks, pushes, and deploys HEAD.
Project commands must enforce source, version, and publication prerequisites before irreversible changes.
Do not rely on this skill as the only guard against an invalid release.

If delivery fails, diagnose and repair through `sync-operator` within existing authorization.
Follow the project version policy when a repair requires another release.

Check actual publication and installation before reporting a release complete.
An existing Git tag, a successful push, or branch delivery alone does not prove package publication.
Keep the loop stopped until recovery succeeds. Resume only when the user requested continuous operation.
