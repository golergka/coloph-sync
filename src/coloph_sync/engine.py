"""Local integration and deployment engine.

Project commands own checks and deployment internals.
"""

import json
import os
import signal
import subprocess
import time
import uuid
from collections import deque
from datetime import UTC, datetime

from .config import Config, load_config
from .git import Git, run_checked
from .state import CommitState, read_state
from .storage import lock, read_json, write_json

OUTPUT_TAIL_LIMIT = 4096


def now():
    return datetime.now(UTC).isoformat()


class Engine:
    def __init__(self, config: Config, *, config_path=None):
        self.config = config
        self.config_path = config_path
        self.git = Git(config.root)
        self.directory = self.git.common_dir()
        self.report_path = self.directory / "sync-report.json"
        self.delivery_path = self.directory / "coloph-sync-delivery.json"
        self.stop_path = self.directory / "coloph-sync-stop.json"
        self.owner_path = self.directory / "coloph-sync-owner.json"
        self.report = read_json(self.report_path)
        self.run_id = f"sync-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        self.draining = False
        self.rollback = False
        self.manual_sha = None
        self.mode = "run"
        self.branch = None

    def save(self, phase=None):
        self.report.update(timestamp=now(), sync_run_id=self.run_id)
        if phase:
            self.report.update(current_phase=phase, phase_started_at=now())
            self.report.pop("error", None)
        write_json(self.report_path, self.report)

    def deployed(self):
        delivery = read_json(self.delivery_path)
        if delivery.get("attempt", {}).get("status") == "completed":
            return delivery["attempt"]["sha"]
        return delivery.get("deployed_sha") or self.git.resolve(f"refs/tags/{self.config.deployed_ref}")

    def command(self, command, context, *, sha=None, attempt=None, timeout=None):
        history = read_json(self.delivery_path).get("history", [])
        previous_attempts = [
            {"id": item["id"], "sha": item["sha"]}
            for item in history if item.get("status") == "superseded" and not item.get("resolved_by")
        ]
        env = {
            **os.environ,
            "COLOPH_SYNC_CONTEXT": context,
            "COLOPH_SYNC_RUN_ID": self.run_id,
            "COLOPH_SYNC_COMMIT": sha or self.git.out("rev-parse", "HEAD"),
            "COLOPH_SYNC_ATTEMPT_ID": attempt or "",
            "COLOPH_SYNC_PREVIOUS_ATTEMPTS": json.dumps(previous_attempts),
            "COLOPH_SYNC_DEPLOYED_COMMIT": self.deployed() or "",
            "COLOPH_SYNC_ROLLBACK": "1" if self.rollback else "0",
            "COLOPH_SYNC_MODE": self.mode,
        }
        log = self.directory / f"coloph-sync-{self.run_id}.log"
        with log.open("a") as stream:
            stream.write(f"\n[{now()}] {context}\n")
            stream.flush()
            tail = deque(maxlen=OUTPUT_TAIL_LIMIT)
            live_output = 0
            truncated = False
            ended_with_newline = True

            def output(line):
                nonlocal live_output, truncated, ended_with_newline
                stream.write(line)
                stream.flush()
                tail.extend(line)
                if truncated:
                    return
                remaining = self.config.live_output_limit - live_output
                visible = line[:remaining]
                if visible:
                    print(visible, end="", flush=True)
                    live_output += len(visible)
                    ended_with_newline = visible.endswith("\n")
                if len(visible) == len(line):
                    return
                truncated = True
                if not ended_with_newline:
                    print()
                print(
                    f"Live output truncated after {self.config.live_output_limit} characters. Full log: {log}",
                    flush=True,
                )

            try:
                result = run_checked(
                    command, cwd=self.config.root, env=env, timeout=timeout or self.config.check_timeout, output=output
                )
            finally:
                if truncated:
                    final_tail = "".join(tail)
                    print("Final output tail:")
                    print(final_tail, end="" if final_tail.endswith("\n") else "\n", flush=True)
        result.check_returncode()
        return result.stdout

    def integration_check(self):
        self.save("verify")
        self.report["checks_status"] = "running"
        self.save()
        self.command(self.config.integration_check or self.config.commit_check, "integration")
        self.report["checks_status"] = "passed"
        self.save()

    def refresh_config(self):
        if self.config_path is None:
            return
        updated = load_config(self.config_path)
        for name in ("root", "main_ref", "remote", "deployed_ref", "deploy_tag_prefix"):
            if getattr(updated, name) != getattr(self.config, name):
                raise RuntimeError(f"The repair changed coordinator routing ({name}); review it before restarting")
        self.config = updated

    def reconcile(self, pending):
        """Project commands own remote recovery; the coordinator selects checked work."""
        if not self.config.reconcile_command:
            if self.git.out("rev-parse", "HEAD") == pending["sha"]:
                return "retry"
            result = {"outcome": "replace", "reason": "Deploy repaired HEAD; the project command owns recovery of prior attempts"}
        else:
            self.save("reconcile")
            output = self.command(
                self.config.reconcile_command, "reconcile", sha=pending["sha"], attempt=pending["id"],
                timeout=self.config.deploy_timeout,
            )
            result = json.loads(output)
        if (
            not isinstance(result, dict)
            or result.get("outcome") not in ("delivered", "retry", "replace", "blocked")
            or not isinstance(result.get("reason"), str)
            or not result["reason"].strip()
        ):
            raise ValueError("Reconciliation requires an outcome and a nonempty reason")
        delivery = read_json(self.delivery_path)
        delivery["attempt"]["reconciliation"] = {**result, "at": now()}
        write_json(self.delivery_path, delivery)
        if result["outcome"] == "blocked":
            raise RuntimeError(result["reason"])
        if result["outcome"] == "delivered":
            delivery["attempt"].update(status="completed", completed_at=now())
            write_json(self.delivery_path, delivery)
        if result["outcome"] == "replace":
            head = self.git.out("rev-parse", "HEAD")
            if head == pending["sha"] or not self.git.ancestor(pending["sha"], head):
                raise RuntimeError("The failed deployment needs a checked successor before replacement")
            if self.barrier("HEAD", self.deployed()):
                raise RuntimeError("A replacement cannot bypass an undelivered deployment barrier")
            delivery.setdefault("history", []).append({
                **delivery.pop("attempt"), "status": "superseded", "replacement_sha": head, "closed_at": now(),
            })
            write_json(self.delivery_path, delivery)
        return result["outcome"]

    def barrier(self, branch, deployed):
        # Original pending_deploy_barrier algorithm, using typed body states.
        for sha in self.git.commits(f"{deployed}..{branch}" if deployed else branch):
            if read_state(self.git.message(sha)) != CommitState.DEPLOY_BARRIER:
                continue
            parent = self.git.out("rev-parse", f"{sha}^")
            if deployed and self.git.ancestor(parent, deployed):
                continue
            return sha, parent
        return None

    def metadata_errors(self, range_spec):
        errors = []
        for sha in self.git.commits(range_spec):
            try:
                state = read_state(self.git.message(sha))
                if state is None:
                    errors.append(f"{sha[:10]} missing Sync-State")
                if state == CommitState.DEPLOY_BARRIER:
                    parents = self.git.out("rev-list", "--parents", "-n", "1", sha).split()[1:]
                    if len(parents) != 1 or self.git.out("rev-parse", f"{sha}^{{tree}}") != self.git.out(
                        "rev-parse", f"{parents[0]}^{{tree}}"
                    ):
                        errors.append(f"{sha[:10]} deployment barrier must be empty with one parent")
            except ValueError as exc:
                errors.append(f"{sha[:10]} {exc}")
        return errors

    def merge_in(self):
        self.save("merge")
        entries = self.report.setdefault("branches", {})
        for branch, path in sorted(self.git.worktrees().items()):
            if branch == self.config.main_ref:
                continue
            if self.branch is not None and branch != self.branch:
                continue
            target = self.git.out("rev-parse", "HEAD")
            tip = self.git.resolve(branch)
            if tip is None:
                entries[branch] = {
                    **entries.get(branch, {}),
                    "last_sync_run_id": self.run_id,
                    "last_merge_attempt": {"at": now(), "outcome": "skipped", "reason": "branch disappeared"},
                }
                self.save()
                continue
            previous = entries.get(branch, {})
            entry = {
                **previous,
                "branch_sha": tip,
                "merge_target_sha": target,
                "last_seen_at": now(),
                "last_sync_run_id": self.run_id,
            }
            entries[branch] = entry
            reason = None
            outcome = "skipped"
            if self.git.ancestor(tip, target):
                outcome = "already_merged"
            elif not self.git.worktree_is_clean(path):
                reason = "worktree is dirty"
                entry["reason_code"] = "dirty"
            elif (
                previous.get("branch_sha") == tip
                and previous.get("merge_status") == "not_merged"
                and (
                    previous.get("reason_code") == "metadata"
                    or (previous.get("reason_code") == "conflict" and previous.get("merge_target_sha") == target)
                )
            ):
                reason = previous["merge_reason"]
                outcome = "unchanged"
            else:
                try:
                    state = read_state(self.git.message(tip))
                    if state in (CommitState.WIP, CommitState.FAILED, CommitState.DONT_MERGE):
                        reason = state.value
                        entry["reason_code"] = "state"
                    else:
                        barrier = self.barrier(tip, self.deployed())
                        merge_sha = barrier[1] if barrier else tip
                        base = self.git.out("merge-base", target, merge_sha)
                        errors = self.metadata_errors(f"{base}..{merge_sha}")
                        if errors:
                            reason = "metadata guard failed: " + "; ".join(errors)
                            entry["reason_code"] = "metadata"
                        else:
                            if not self.git.ancestor(merge_sha, target):
                                environment = {**os.environ, "COLOPH_SYNC_AUTOMATIC_MERGE": "1"}
                                result = run_checked(
                                    ["git", "merge", "--no-edit", merge_sha],
                                    cwd=self.config.root,
                                    env=environment,
                                    timeout=self.config.merge_timeout,
                                    output=lambda line: print(line, end="", flush=True),
                                )
                                result.check_returncode()
                                if read_state(self.git.message("HEAD")) not in (
                                    CommitState.PASSED,
                                    CommitState.DEPLOY_BARRIER,
                                ):
                                    raise RuntimeError(
                                        "The merge did not produce a passed commit; install the commit hook and repair before resuming"
                                    )
                            if barrier:
                                reason = f"merged up to {merge_sha[:10]} due to deployment barrier {barrier[0][:10]}; waiting for deployment"
                                outcome = "partial_merged"
                                entry["reason_code"] = "barrier"
                            else:
                                outcome = "merged"
                except ValueError as exc:
                    reason = f"metadata guard failed: {exc}"
                    entry["reason_code"] = "metadata"
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    if self.git.resolve("MERGE_HEAD"):
                        self.git.out("merge", "--abort")
                    reason = "merge timed out" if isinstance(exc, subprocess.TimeoutExpired) else "merge failed"
                    entry["reason_code"] = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "conflict"
                    outcome = "failed"
            entry.update(
                merge_status="not_merged" if reason else "merged",
                merge_reason=reason,
                last_merge_attempt={"at": now(), "outcome": outcome},
            )
            if not reason:
                entry.pop("reason_code", None)
                entry["merged_at"] = now()
            self.save()

        self.refresh_config()

    def remote_ref(self, ref):
        output = self.git.out("ls-remote", self.config.remote, ref)
        for line in output.splitlines():
            sha, name = line.split()
            if name == ref:
                return sha
        return None

    def publish(self, delivery):
        attempt = delivery["attempt"]
        sha = attempt["sha"]
        immutable = f"refs/tags/{self.config.deploy_tag_prefix}/{attempt['id']}"
        floating = f"refs/tags/{self.config.deployed_ref}"
        found = self.remote_ref(immutable)
        if found not in (None, sha):
            raise RuntimeError(f"Deployment tag conflict: {immutable}")
        self.git.out("update-ref", immutable, sha)
        if found is None:
            self.git.out("push", self.config.remote, f"{immutable}:{immutable}", timeout=120)
        previous = attempt["previous_remote"]
        found = self.remote_ref(floating)
        if found != sha:
            if found != previous:
                raise RuntimeError("Deployed ref changed concurrently; reconcile before resuming")
            self.git.out(
                "push",
                f"--force-with-lease={floating}:{previous or ''}",
                self.config.remote,
                f"{sha}:{floating}",
                timeout=120,
            )
        self.git.out("update-ref", floating, sha)
        attempt["status"] = "published"
        delivery["deployed_sha"] = sha
        write_json(self.delivery_path, delivery)
        self.report["deploy_sha"] = sha
        self.save("done")

    def deploy(self, sha):
        delivery = read_json(self.delivery_path)
        previous = delivery.get("attempt", {})
        if sha != self.git.out("rev-parse", "HEAD") and not (
            previous.get("sha") == sha and previous.get("status") == "completed"
        ):
            raise RuntimeError("Deployment tooling and payload must come from HEAD; an older commit cannot be deployed here")
        if previous and previous["status"] != "published":
            if previous["sha"] != sha:
                raise RuntimeError(
                    f"Resolve deploy attempt {previous['id']} for {previous['sha']} before deploying another commit"
                )
            attempt = previous
            self.rollback = attempt.get("rollback", False)
        else:
            deployed = self.deployed()
            if deployed and not self.rollback and not self.git.ancestor(deployed, sha):
                raise RuntimeError("Automatic rollback is not supported; reconcile deployment state explicitly")
            if deployed == sha:
                self.report["deploy_sha"] = sha
                self.save("done")
                return
            attempt = {
                "id": f"{self.run_id}-{uuid.uuid4().hex[:8]}",
                "sha": sha,
                "status": "running",
                "previous_remote": self.remote_ref(f"refs/tags/{self.config.deployed_ref}"),
                "rollback": self.rollback,
            }
            delivery["attempt"] = attempt
            write_json(self.delivery_path, delivery)
        if attempt["status"] != "completed":
            if sha != self.git.out("rev-parse", "HEAD"):
                raise RuntimeError("Deployment tooling and payload must come from HEAD; an older commit cannot be deployed here")
            self.save("deploy")
            self.command(
                self.config.deploy_command, "deploy", sha=sha, attempt=attempt["id"], timeout=self.config.deploy_timeout
            )
            attempt.update(status="completed", completed_at=now())
            for item in delivery.get("history", []):
                if item.get("status") == "superseded" and not item.get("resolved_by"):
                    item["resolved_by"] = attempt["id"]
            write_json(self.delivery_path, delivery)
        self.save("publish")
        self.publish(delivery)

    def cycle(self, *, deploy_only=False, push_deploy_only=False, repair_pending_deploy=False):
        if self.git.out("branch", "--show-current") != self.config.main_ref:
            raise RuntimeError(f"Run the coordinator on {self.config.main_ref}")
        if self.git.out("status", "--porcelain"):
            raise RuntimeError("The coordinator checkout must be clean")
        if read_state(self.git.message("HEAD")) not in (CommitState.PASSED, CommitState.DEPLOY_BARRIER):
            raise RuntimeError("The integration branch must have a checked commit before running")
        pending = read_json(self.delivery_path).get("attempt", {})
        if pending and pending["status"] != "published":
            self.rollback = pending.get("rollback", False)
            if self.manual_sha and self.git.resolve(self.manual_sha) != pending["sha"]:
                raise RuntimeError("A different manual target cannot replace an unresolved deployment")
            if pending["status"] == "completed":
                if repair_pending_deploy:
                    raise RuntimeError("A completed deploy only needs publication retry; do not merge a repair")
                self.deploy(pending["sha"])
            else:
                if self.branch and not deploy_only and not push_deploy_only:
                    repair_sha = self.git.resolve(self.branch)
                    if not repair_sha:
                        raise RuntimeError(f"Repair branch does not exist: {self.branch}")
                    self.merge_in()
                    if not self.git.ancestor(repair_sha, "HEAD"):
                        raise RuntimeError(f"Repair branch was not fully merged: {self.branch}")
                if self.git.out("rev-parse", "HEAD") != pending["sha"]:
                    self.integration_check()
                outcome = self.reconcile(pending)
                if outcome == "retry" and self.git.out("rev-parse", "HEAD") != pending["sha"]:
                    raise RuntimeError(
                        "The repair will deploy HEAD, not the failed commit. "
                        "Reconcile the old remote operation before replacing it: "
                        "the project reconcile_command must confirm delivered or replace."
                    )
                if outcome != "replace":
                    self.deploy(pending["sha"])
            if deploy_only or self.git.out("rev-parse", "HEAD") == pending["sha"]:
                return
            self.rollback = False
        if self.config.preflight_command:
            self.save("preflight")
            self.command(self.config.preflight_command, "preflight")
        if not deploy_only:
            if not push_deploy_only:
                self.merge_in()
            self.integration_check()
        sha = self.git.resolve(self.manual_sha) if self.manual_sha else self.git.out("rev-parse", "HEAD")
        if not sha:
            raise ValueError("Deployment target does not exist")
        if not deploy_only:
            self.save("push")
            self.git.out("push", self.config.remote, self.config.main_ref)
        else:
            self.git.out("fetch", self.config.remote, self.config.main_ref)
            if not self.git.ancestor(sha, f"{self.config.remote}/{self.config.main_ref}"):
                raise RuntimeError("Push the deployment target before a manual deploy")
        self.deploy(sha)

    def run(self, *, once=False, deploy_only=False, push_deploy_only=False, repair_pending_deploy=False):
        with lock(self.directory / "sync-test-push.lock"):
            owner = {"pid": os.getpid(), "id": self.run_id}
            write_json(self.owner_path, owner)
            old_signal = signal.signal(signal.SIGTERM, lambda *_: setattr(self, "draining", True))
            try:
                while True:
                    try:
                        self.cycle(
                            deploy_only=deploy_only,
                            push_deploy_only=push_deploy_only,
                            repair_pending_deploy=repair_pending_deploy,
                        )
                    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
                        phase = self.report.get("current_phase", "startup")
                        if phase == "verify":
                            self.report["checks_status"] = "failed"
                        self.report.update(
                            current_phase="error", error={"phase": phase, "at": now(), "message": str(exc)}
                        )
                        self.save()
                        raise
                    if once or deploy_only or push_deploy_only:
                        return
                    deadline = time.monotonic() + self.config.interval
                    while time.monotonic() < deadline:
                        if self.draining or read_json(self.stop_path).get("id") == owner["id"]:
                            return
                        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
                    if self.draining or read_json(self.stop_path).get("id") == owner["id"]:
                        return
                    self.run_id = f"sync-{uuid.uuid4().hex}"
            finally:
                signal.signal(signal.SIGTERM, old_signal)
                self.owner_path.unlink(missing_ok=True)
