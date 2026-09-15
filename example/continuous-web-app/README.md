# Continuous web app example

This example represents a small static web application. Every integrated commit updates the live application.
The application has no release versions. The deployed Git commit is its version.

Coloph-sync runs the checks, pushes `main`, calls the delivery command, and records the confirmed commit.
The project check validates the site. The project delivery command copies the site to its web root.

Copy this directory into a new Git repository. Add coloph-sync as a project development dependency. Then run:

```sh
uv run coloph-sync init
uv run coloph-sync init --install-hooks
```

Commit the generated `.githooks/commit-msg` file with the application.

Set `WEB_ROOT` in the coordinator environment. Keep the `main` checkout clean and run `uv run coloph-sync run` there.
The user or agent host creates and assigns linked worktrees. Each development agent must stay in its assigned worktree.

To test the result, serve `$WEB_ROOT/current`. The page must show the text “Continuous web app example.”
