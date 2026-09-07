"""CLI and agent-facing status contract."""

import argparse
import json
import subprocess
import sys
import time
from importlib.resources import files
from pathlib import Path

from .config import load_config
from .engine import Engine
from .hooks import check, install, uninstall
from .state import CommitState, read_state
from .storage import read_json, write_json


def status(engine, branch=None, commit=None):
    git = engine.git
    branch = branch or git.out("branch", "--show-current")
    sha = git.resolve(commit or branch)
    if not sha:
        raise ValueError("Specify an existing branch or commit")
    report = read_json(engine.report_path)
    entry = report.get("branches", {}).get(branch, {})
    main = git.resolve(engine.config.main_ref)
    deployed = engine.deployed()
    merged = bool(main and git.ancestor(sha, main))
    delivered = bool(deployed and git.ancestor(sha, deployed))
    state = read_state(git.message(sha))
    reason = None
    if not merged:
        if state in (CommitState.WIP, CommitState.FAILED, CommitState.DONT_MERGE):
            reason = state.value
        elif entry.get("branch_sha") == sha:
            reason = entry.get("merge_reason")
    actionable = bool(reason and entry.get("reason_code") != "barrier")
    error = report.get("error")
    checks = report.get("checks_status")
    verdict = (
        "action needed"
        if checks == "failed"
        else "deployed"
        if delivered
        else "action needed"
        if actionable or error
        else "merged"
        if merged
        else "pending"
    )
    return {
        "branch": branch,
        "commit": sha,
        "merged": merged,
        "deployed": delivered,
        "verdict": verdict,
        "reason": reason,
        "last_sync": report.get("timestamp"),
        "phase": report.get("current_phase"),
        "error": error,
        "checks": checks,
        "last_merge_attempt": entry.get("last_merge_attempt"),
        "publication_pending": read_json(engine.delivery_path).get("attempt", {}).get("status") == "completed",
    }


def render(value):
    print(
        f"Verdict: {value['verdict']}\nBranch: {value['branch']}\nMerged: {'yes' if value['merged'] else 'no'}\n"
        f"Deployed: {'yes' if value['deployed'] else 'no'}"
    )
    print(f"Tip: {value['commit']}")
    if value["reason"]:
        print(f"Reason: {value['reason']}")
    if value["phase"]:
        print(f"Sync loop phase: {value['phase']}")
    if value["checks"]:
        print(f"Checks: {value['checks']}")
    if value["error"]:
        print(f"Last sync error: {value['error']['message']}")
    if value["publication_pending"]:
        print("Deployment confirmed; publication pending")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Commit checks, integration, and deployment coordination")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--once", action="store_true")
    run.add_argument("--branch", help="Restrict integration to one local worktree branch")
    run.add_argument("--push-deploy-only", action="store_true")
    deploy = sub.add_parser("deploy", help="Deploy through the shared coordinator")
    deploy.add_argument("--commit")
    deploy.add_argument("--rollback", action="store_true", help="Explicit operator recovery; never used by the loop")
    sub.add_parser("stop", help="Drain the current cycle and prevent the next cycle")
    sub.add_parser("logs")
    sub.add_parser("install-hooks")
    sub.add_parser("uninstall-hooks")
    sub.add_parser("message-state", help="Read a commit message from stdin and print its state")
    hook = sub.add_parser("hook")
    hook.add_argument("message", type=Path)
    state = sub.add_parser("state", help="Read the typed commit state")
    state.add_argument("ref", nargs="?", default="HEAD")
    skill = sub.add_parser("skill", help="Print the bundled operating instructions")
    skill.add_argument("name", choices=["contributor", "operator", "finish"])
    for name in ("status", "wait"):
        p = sub.add_parser(name)
        p.add_argument("--branch")
        p.add_argument("--commit")
        p.add_argument("--all", action="store_true")
        p.add_argument("--until", choices=["merged", "deployed"], default="deployed")
        p.add_argument("--timeout", type=int, default=14400)
    args = parser.parse_args(argv)
    try:
        if args.command == "message-state":
            state = read_state(sys.stdin.read())
            print(state.value if state else "unmarked")
            return 0
        if args.command == "skill":
            print(files("coloph_sync").joinpath("skills", args.name, "SKILL.md").read_text())
            return 0
        config = load_config(args.config)
        if args.command == "hook":
            return check(config, args.message.resolve())
        if args.command == "install-hooks":
            install(config)
            print("Installed commit-msg hook. Link agent instructions to: coloph-sync skill contributor")
            return 0
        if args.command == "uninstall-hooks":
            uninstall(config)
            return 0
        engine = Engine(config)
        if args.command in ("run", "deploy"):
            engine.manual_sha = getattr(args, "commit", None)
            engine.rollback = getattr(args, "rollback", False)
            engine.mode = args.command
            engine.branch = getattr(args, "branch", None)
            if engine.rollback and not engine.manual_sha:
                raise ValueError("An explicit rollback requires --commit")
            engine.run(
                once=getattr(args, "once", False),
                deploy_only=args.command == "deploy",
                push_deploy_only=getattr(args, "push_deploy_only", False),
            )
        elif args.command == "stop":
            owner = read_json(engine.owner_path)
            if not owner:
                print("No coordinator is running")
            else:
                write_json(engine.stop_path, {"id": owner["id"]})
                print("Stop requested: the current cycle will finish")
        elif args.command == "logs":
            logs = sorted(engine.directory.glob("coloph-sync-*.log"), key=lambda path: path.stat().st_mtime)
            if logs:
                print(logs[-1].read_text(), end="")
        elif args.command == "state":
            value = read_state(engine.git.message(args.ref))
            print(value.value if value else "unmarked")
        else:
            deadline = time.monotonic() + args.timeout
            while True:
                branches = (
                    engine.git.out("for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines()
                    if args.all
                    else [args.branch]
                )
                values = [status(engine, branch, args.commit) for branch in branches]
                if args.json:
                    print(json.dumps(values if args.all else values[0]))
                else:
                    for value in values:
                        render(value)
                if args.command != "wait" or all(value[args.until] for value in values):
                    return 0
                if any(value["verdict"] == "action needed" for value in values):
                    return 1
                if time.monotonic() >= deadline:
                    return 1
                time.sleep(min(5, max(0, deadline - time.monotonic())))
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; reconcile any unfinished deploy attempt before resuming", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
