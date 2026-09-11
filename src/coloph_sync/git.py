"""Bounded Git operations."""

import os
import signal
import subprocess
import time
from pathlib import Path
from threading import Thread


def run_checked(cmd, *, cwd, timeout=600, env=None, output=None):
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True
    )
    chunks = []

    def consume():
        for line in proc.stdout:
            chunks.append(line)
            if output:
                output(line)

    reader = Thread(target=consume)
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        proc.wait(timeout=timeout)
        reader.join(max(0, deadline - time.monotonic()))
        if reader.is_alive():
            raise subprocess.TimeoutExpired(cmd, timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # The process group already exited.
        proc.wait()
        reader.join()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(chunks))


class Git:
    def __init__(self, root: Path):
        self.root = root

    def result(self, *args, timeout=60):
        return run_checked(["git", *args], cwd=self.root, timeout=timeout)

    def out(self, *args, timeout=60):
        result = self.result(*args, timeout=timeout)
        result.check_returncode()
        return result.stdout.strip()

    def resolve(self, ref):
        result = self.result("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if result.returncode == 1:
            return None
        result.check_returncode()
        return result.stdout.strip()

    def ancestor(self, ancestor, descendant):
        result = self.result("merge-base", "--is-ancestor", ancestor, descendant)
        if result.returncode not in (0, 1):
            result.check_returncode()
        return result.returncode == 0

    def message(self, sha):
        return self.out("log", "-1", "--format=%B", sha)

    def commits(self, range_spec):
        return self.out("rev-list", "--reverse", range_spec).splitlines()

    def common_dir(self):
        path = Path(self.out("rev-parse", "--git-common-dir"))
        return path if path.is_absolute() else (self.root / path).resolve()

    def worktrees(self, *, include_root=False):
        self.out("worktree", "prune")
        output = self.out("worktree", "list", "--porcelain", "-z")
        result = {}
        for record in output.split("\0\0"):
            items = dict(field.split(" ", 1) for field in record.split("\0") if " " in field)
            branch, path = items.get("branch", ""), items.get("worktree", "")
            if (
                branch.startswith("refs/heads/")
                and Path(path).is_dir()
                and (include_root or Path(path).resolve() != self.root)
            ):
                result[branch.removeprefix("refs/heads/")] = Path(path)
        return result

    def worktree_is_clean(self, path):
        return not self.out("-C", str(path), "status", "--porcelain")
