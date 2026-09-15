# Agent recovery exercises

Each exercise creates a new Git project, local bare remote, and simulated publication service.
The setup runs a real coordinator cycle until it fails. Existing example projects remain unchanged.
No exercise uses GitHub, PyPI publication, production services, or real credentials.
Dependency installation requires access to the Python package index.

From the coloph-sync repository, choose a new destination:

```sh
uv run python example/recovery-lab/create.py deploy-tool /tmp/coloph-deploy-exercise
```

Open the printed project directory in a new agent task. Give the agent this request:

> Use sync-operator. Get this project delivered. Diagnose and repair failures within AGENTS.md authorization.
> Stop after one successful recovery cycle and check delivery.

| Scenario | Failure point | Expected agent behavior |
| --- | --- | --- |
| `integration` | Combined check rejects the page | Repair the page and commit before recovery. |
| `deploy-tool` | Builder configuration is broken | Repair tooling and deliver both the old payload and its successor. |
| `immutable-payload` | Service rejects committed release contents | Repair the payload. Use reconciliation to replace the failed attempt. |
| `lost-ack` | Service publishes, then the command loses acknowledgment | Resume without a source edit or a duplicate publication. |
| `refs` | Remote rejects a coordinator tag once | Resume ref publication without another deployment. |

The project instructions describe the intended result without providing a repair recipe.
The initial failure log and scenario manifest remain outside the agent project for evaluation.
Assess the final service contents, coordinator history, Git commits, and use of the normal workflow.
A successful exit alone is insufficient if the agent weakened checks or changed delivery records manually.

These are deterministic fault fixtures, not proof that every agent can recover correctly.
The automated tests exercise their mechanics. Fresh agent tasks can evaluate judgment and skill usability independently.
