"""One hook owner for ordinary and merge commits."""

import os
from pathlib import Path

from .config import Config
from .git import Git, run_checked
from .state import CommitState, read_state, write_state
from .storage import lock, write_json


def check(config: Config, message_path: Path) -> int:
    git = Git(config.root)
    local = Path(git.out("rev-parse", "--absolute-git-dir"))
    with lock(local / "coloph-sync-hook.lock"):
        message = message_path.read_text()
        state = read_state(message)
        merge = git.resolve("MERGE_HEAD") is not None
        if merge:
            parent_state = read_state(git.message("HEAD"))
            if parent_state in (None, CommitState.WIP, CommitState.FAILED):
                raise ValueError(
                    "Finish the current commit checks before merging; a checked dont-merge scaffold is allowed"
                )
            if state in (CommitState.WIP, CommitState.DEPLOY_BARRIER, CommitState.DONT_MERGE):
                raise ValueError("A merge commit cannot request a checkpoint or barrier state")
        elif state == CommitState.DEPLOY_BARRIER:
            if git.out("diff", "--cached", "--name-only"):
                raise ValueError("A deployment barrier must be empty")
            message_path.write_text(write_state(message, state))
            return 0
        elif state == CommitState.WIP:
            message_path.write_text(write_state(message, state))
            return 0

        command = (config.merge_check or config.commit_check) if merge else config.commit_check
        environment = {
            **os.environ,
            "COLOPH_SYNC_CONTEXT": "merge" if merge else "commit",
            "COLOPH_SYNC_MESSAGE": str(message_path.resolve()),
            "COLOPH_SYNC_REQUESTED_STATE": (state or CommitState.PASSED).value,
        }
        result = run_checked(
            command,
            cwd=config.root,
            env=environment,
            timeout=config.check_timeout,
            output=lambda line: print(line, end="", flush=True),
        )
        write_json(local / "coloph-sync-check.json", {"exit_code": result.returncode, "output": result.stdout})
        if result.returncode not in (0, 1):
            return 1
        if result.returncode == 1 and merge and os.environ.get("COLOPH_SYNC_AUTOMATIC_MERGE") == "1":
            return 1
        final_state = (
            CommitState.FAILED
            if result.returncode
            else (CommitState.DONT_MERGE if state == CommitState.DONT_MERGE else CommitState.PASSED)
        )
        # Project checks may append their own structured reports.
        message_path.write_text(write_state(message_path.read_text(), final_state))
        return 0


def install(config: Config):
    git = Git(config.root)
    custom = git.result("config", "--get", "core.hooksPath")
    if custom.returncode not in (0, 1):
        custom.check_returncode()
    hooks = Path(custom.stdout.strip()) if custom.returncode == 0 else git.common_dir() / "hooks"
    if not hooks.is_absolute():
        hooks = config.root / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "commit-msg"
    signature = "# coloph-sync managed hook"
    previous = hooks / "commit-msg.before-coloph-sync"
    if hook.exists() and signature not in hook.read_text():
        if previous.exists():
            raise ValueError(f"Cannot preserve another existing hook at {previous}")
        hook.rename(previous)
    hook.write_text(
        f"#!/bin/sh\n{signature}\n"
        'previous="$(dirname "$0")/commit-msg.before-coloph-sync"\n'
        'if [ -x "$previous" ]; then "$previous" "$@" || exit $?; fi\n'
        'root="$(git rev-parse --show-toplevel)" || exit $?\n'
        'cd "$root" || exit $?\n'
        'exec uv run coloph-sync hook "$@"\n'
    )
    hook.chmod(0o755)


def uninstall(config: Config):
    git = Git(config.root)
    custom = git.result("config", "--get", "core.hooksPath")
    hooks = Path(custom.stdout.strip()) if custom.returncode == 0 else git.common_dir() / "hooks"
    if not hooks.is_absolute():
        hooks = config.root / hooks
    hook, previous = hooks / "commit-msg", hooks / "commit-msg.before-coloph-sync"
    if hook.exists() and "# coloph-sync managed hook" in hook.read_text():
        hook.unlink()
        if previous.exists():
            previous.rename(hook)
