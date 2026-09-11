---
name: coloph-sync-finish
description: Determine whether a contributor's change has merged and deployed, then complete project-specific production validation.
---

Run `coloph-sync status` for the current branch, or select the intended commit explicitly.
Distinguish merged from deployed. A successful local commit is not completed delivery.
Repair actionable branch failures through the contributor workflow.
Use `coloph-sync wait --commit <sha>` when the host permits foreground waiting.
Otherwise inspect status through the host's supported reminder mechanism.

After deployment, run the repository's relevant production smoke procedure.
A deployment record proves historical success, not continuous service health.
Report the requested scope, delivered scope, merge state, deployment state, and smoke result.
Do not claim completion while a required check or smoke is unresolved.
