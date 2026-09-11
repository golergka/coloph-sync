"""Explicit integration of branches that predate commit-state checks."""

import os
import subprocess
from datetime import UTC, datetime

from .git import Git, run_checked
from .hooks import managed_hook_installed
from .state import read_state
from .storage import read_json, write_json


def candidates(git: Git, main_ref: str) -> list[str]:
    """Return active unmerged branches with legacy unmarked commits."""
    main = git.resolve(main_ref)
    if not main:
        return []
    result = []
    for branch in sorted(git.worktrees(include_root=True)):
        tip = git.resolve(branch)
        if branch == main_ref or not tip or git.ancestor(tip, main):
            continue
        base = git.out("merge-base", main, tip)
        for sha in git.commits(f"{base}..{tip}"):
            try:
                if read_state(git.message(sha)) is None:
                    result.append(branch)
                    break
            except ValueError:
                # Invalid metadata needs repair; it is not an adoption candidate.
                break
    return result


def hint(git: Git, main_ref: str, *, limit=8) -> str | None:
    names = candidates(git, main_ref)
    if not names:
        return None
    shown = ", ".join(names[:limit])
    remainder = len(names) - limit
    if remainder > 0:
        shown += f", and {remainder} more"
    return f"Existing worktree branches may need adoption: {shown}\nRun: uv run coloph-sync adopt --all"


def adopt(config, branches: list[str]) -> list[tuple[str, str | None]]:
    """Merge selected legacy branches through the normal merge hook.

    Each successful merge creates a checked Git boundary while the shared record
    preserves the adoption audit trail.
    """
    git = Git(config.root)
    if git.out("branch", "--show-current") != config.main_ref:
        raise RuntimeError(f"Run adoption from the clean {config.main_ref} checkout")
    if git.out("status", "--porcelain"):
        raise RuntimeError("The adoption checkout must be clean")
    if not managed_hook_installed(config):
        raise RuntimeError("Install the commit hook before adopting branches")

    directory = git.common_dir()
    if read_json(directory / "coloph-sync-owner.json"):
        raise RuntimeError("Stop the coordinator before adopting branches")
    available = set(candidates(git, config.main_ref))
    records = read_json(directory / "coloph-sync-adoptions.json")
    adopted = records.setdefault("adoptions", {})
    results = []
    for branch in branches:
        if branch not in available:
            results.append((branch, "does not need adoption or is not an active worktree branch"))
            continue
        target = git.out("rev-parse", "HEAD")
        tip = git.resolve(branch)
        try:
            result = run_checked(
                ["git", "merge", "--no-ff", "--no-edit", branch],
                cwd=config.root,
                env={**os.environ, "COLOPH_SYNC_AUTOMATIC_MERGE": "1", "COLOPH_SYNC_ADOPTION": "1"},
                timeout=config.merge_timeout,
            )
            result.check_returncode()
            adopted[tip] = {
                "branch": branch,
                "target": target,
                "merged": git.out("rev-parse", "HEAD"),
                "at": datetime.now(UTC).isoformat(),
            }
            write_json(directory / "coloph-sync-adoptions.json", records)
            results.append((branch, None))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if git.resolve("MERGE_HEAD"):
                git.out("merge", "--abort")
            results.append((branch, "merge check failed or the branch conflicts with main"))
    return results
