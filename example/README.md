# Continuously deployed web app

This example shows a web app that deploys every commit integrated into `main`.
It contrasts with the versioned-package policy in the parent project.

Coloph-sync runs the checks, integrates worktree branches, pushes `main`, and calls `scripts/deploy`.
The app owner implements both scripts and configures the hosting service.

The example deployment command sends the exact commit to a hosting service.
It then waits until that service reports the commit as live.
A retry with the same attempt identifier continues to check the same deployment.

To adapt this example:

1. Copy `coloph-sync.toml` and `scripts/` into the app repository.
2. Replace the placeholder check command with the app test command.
3. Replace the example hosting URLs with the real service API.
4. Provide `HOST_API_URL` and `HOST_API_TOKEN` in the loop environment.
5. Run `coloph-sync init`, then `coloph-sync install-hooks`.
6. Run `coloph-sync run` from the clean main checkout.

The hosting API in this example has two operations:

- `PUT /deployments/{attempt}` starts or resumes deployment of the supplied commit.
- `GET /deployments/{attempt}` returns JSON with `commit` and `status` fields.

The deployment command exits successfully only when `status` is `live` for the requested commit.
This API is an example contract, not a service that coloph-sync provides.
