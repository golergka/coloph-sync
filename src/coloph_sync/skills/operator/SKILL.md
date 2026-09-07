---
name: coloph-sync-operator
description: Start, stop, inspect, or recover the local coloph-sync integration and deployment coordinator.
---

Operate only the designated integration checkout with repository authorization.
Run `coloph-sync run` in the foreground. A terminal multiplexer or service manager can host it.
Use `coloph-sync stop` to finish the current cycle and prevent another cycle.
Do not edit the checkout while the coordinator owns it. Wait for its process to exit.
Read `coloph-sync logs` and `coloph-sync status --all` for evidence.

A failed cycle stops the loop. Investigate its recorded phase and output.
Branch conflicts and invalid metadata leave that branch out; other eligible branches continue.
Check failures stop publication. Deploy failures do not prove that production stayed unchanged.
The deployment command must reconcile repeated calls with the same attempt ID and target.
Resume with `coloph-sync run --once`; it resolves an unfinished deployment before admitting new work.
A completed deployment with failed ref publication retries publication without running deployment again.
Do not move deployment tags manually or start an independent deploy process.
For an intentional manual deployment of the current pushed main commit, use `coloph-sync deploy`.
Automatic rollback and conflict resolution are not supported.
