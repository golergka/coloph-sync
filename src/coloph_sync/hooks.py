"""One hook owner for ordinary and merge commits."""

import os
from pathlib import Path

from .config import Config
from .git import Git, run_checked
from .state import CommitState, read_state, write_state
from .storage import lock, write_json


def managed_hook_path(config: Config) -> Path:
    git = Git(config.root)
    custom = git.result("config", "--get", "core.hooksPath")
    if custom.returncode not in (0, 1):
        custom.check_returncode()
    setup = "Run: uv run coloph-sync init --install-hooks"
    if custom.returncode == 1:
        raise ValueError(f"No version-controlled Git hook directory is configured. {setup}")
    hooks = Path(custom.stdout.strip())
    if not hooks.is_absolute():
        hooks = config.root / hooks
    hooks = hooks.resolve()
    root = config.root.resolve()
    try:
        relative = hooks.relative_to(root)
    except ValueError:
        raise ValueError(f"core.hooksPath must point inside the project. {setup}") from None
    if relative.parts and relative.parts[0] == ".git":
        raise ValueError(f"core.hooksPath must point to version-controlled project files. {setup}")
    return hooks / "commit-msg"


def managed_hook_installed(config: Config) -> bool:
    hook = managed_hook_path(config)
    return hook.exists() and "# coloph-sync managed hook" in hook.read_text()


def ignored_hook_rule(config: Config, hook: Path) -> str | None:
    relative = hook.relative_to(config.root.resolve())
    git = Git(config.root)
    tracked = git.result("ls-files", "--error-unmatch", "--", str(relative))
    if tracked.returncode == 0:
        return None
    if tracked.returncode != 1:
        tracked.check_returncode()
    ignored = git.result("check-ignore", "-v", "--no-index", "--", str(relative))
    if ignored.returncode == 1:
        return None
    ignored.check_returncode()
    return ignored.stdout.strip()


def check(config: Config, message_path: Path) -> int:
    git = Git(config.root)
    local = Path(git.out("rev-parse", "--absolute-git-dir"))
    with lock(local / "coloph-sync-hook.lock"):
        message = message_path.read_text()
        state = read_state(message)
        merge = git.resolve("MERGE_HEAD") is not None
        if merge:
            parent_state = read_state(git.message("HEAD"))
            if parent_state in (None, CommitState.WIP, CommitState.FAILED) and not os.environ.get("COLOPH_SYNC_ADOPTION"):
                raise ValueError(
                    "Complete the current commit checks before merging; a checked dont-merge scaffold is allowed"
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


def install(config: Config, *, configure=False):
    git = Git(config.root)
    if configure:
        git.out("config", "--local", "core.hooksPath", ".githooks")
    hook = managed_hook_path(config)
    hook.parent.mkdir(parents=True, exist_ok=True)
    signature = "# coloph-sync managed hook"
    previous = hook.parent / "commit-msg.before-coloph-sync"
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
    return hook


def uninstall(config: Config):
    hook = managed_hook_path(config)
    previous = hook.parent / "commit-msg.before-coloph-sync"
    if hook.exists() and "# coloph-sync managed hook" in hook.read_text():
        hook.unlink()
        if previous.exists():
            previous.rename(hook)
