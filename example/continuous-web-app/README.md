# Continuous web app example

This example represents a small static web application. Every integrated commit updates the live application.
The application has no release versions. The deployed Git commit is its version.

Coloph-sync runs the checks, pushes `main`, calls the delivery command, and records the confirmed commit.
The project check validates the site. The project delivery command copies the site to its web root.

Copy this directory into a new Git repository. Install a fixed coloph-sync version. Then run:

```sh
coloph-sync init
coloph-sync install-hooks
```

Set `WEB_ROOT` in the coordinator environment. Keep the `main` checkout clean and run `coloph-sync run` there.
The user or agent host creates and assigns linked worktrees. Each development agent must stay in its assigned worktree.

To test the result, serve `$WEB_ROOT/current`. The page must show the text “Continuous web app example.”
