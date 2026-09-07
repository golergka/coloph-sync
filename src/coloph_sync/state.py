"""Commit-body protocol shared by admission and commit hooks."""

from enum import StrEnum


class CommitState(StrEnum):
    WIP = "wip"
    PASSED = "passed"
    FAILED = "failed"
    DONT_MERGE = "dont-merge"
    DEPLOY_BARRIER = "deploy-barrier"


MARKER = "Sync-State:"


def read_state(message: str) -> CommitState | None:
    lines = [line for line in message.splitlines()[1:] if line.startswith(MARKER)]
    if len(lines) > 1:
        raise ValueError("A commit must contain exactly one Sync-State line")
    if not lines:
        return None
    return CommitState(lines[0][len(MARKER) :].strip())


def write_state(message: str, state: CommitState) -> str:
    read_state(message)  # Reject conflicting input rather than silently repairing it.
    lines = [line for line in message.splitlines() if not line.startswith(MARKER)]
    return "\n".join(lines).rstrip() + f"\n\n{MARKER} {state.value}\n"
