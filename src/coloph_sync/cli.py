"""CLI and agent-facing status contract."""

import argparse
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from .adoption import adopt, candidates, hint
from .config import load_config
from .engine import Engine
from .git import Git
from .hooks import check, install, uninstall
from .state import CommitState, read_state
from .storage import read_json, write_json

SKILLS = ("contributor", "merge-main", "operator", "finish")
CONFIG_TEMPLATE = """# Coloph-sync owns commit checks, integration, and calls to the deployment command.
# This project owns the commands, release policy, deployment service, and success criteria.
# A package can publish only after a version change. A continuously deployed app can deploy every integrated commit.
main_ref = "main"
remote = "origin"
commit_check = ["./scripts/check", "commit"]
merge_check = ["./scripts/check", "merge"]
integration_check = ["./scripts/check", "integration"]
deploy_command = ["./scripts/deploy"]
"""


def _skill_files(root: Path):
    return {
        root / ".agents" / "skills" / f"sync-{name}" / "SKILL.md": files("coloph_sync")
        .joinpath("skills", name, "SKILL.md")
        .read_text(encoding="utf-8")
        for name in SKILLS
    }


def install_skills(root: Path):
    skill_files = _skill_files(root)
    created = []
    for name in SKILLS:
        legacy = root / ".agents" / "skills" / f"coloph-sync-{name}" / "SKILL.md"
        if legacy.exists():
            legacy.unlink()
            try:
                legacy.parent.rmdir()
            except OSError:
                pass
    for path, content in skill_files.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(path)
    return created


def check_skills(root: Path):
    for path, content in _skill_files(root).items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise ValueError(
                "Coloph-sync skills are missing or out of date. "
                "Run: uv run coloph-sync install-skills"
            )


def initialize(config: Path):
    root = config.parent
    skill_files = _skill_files(root)
    for path, content in skill_files.items():
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Skill file differs: {path}; reconcile or move it before initializing")
    created = []
    if not config.exists():
        config.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        created.append(config)
    created.extend(install_skills(root))
    return created


def status(engine, branch=None):
    git = engine.git
    branch = branch or git.out("branch", "--show-current")
    sha = git.resolve(branch)
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
    sub.add_parser("init", help="Create configuration and install host-project agent workflows")
    run = sub.add_parser("run")
    run.add_argument("--once", action="store_true")
    run.add_argument("--branch", help="Restrict integration to one local worktree branch")
    run.add_argument("--push-deploy-only", action="store_true", help="Skip merges, then check, push, and deploy main")
    deploy = sub.add_parser("deploy", help="Deploy through the shared coordinator")
    deploy.add_argument("--commit")
    deploy.add_argument("--rollback", action="store_true", help="Explicit operator recovery; never used by the loop")
    adopt_parser = sub.add_parser("adopt", help="Check and integrate branches created before coloph-sync")
    adopt_group = adopt_parser.add_mutually_exclusive_group(required=True)
    adopt_group.add_argument("--branch")
    adopt_group.add_argument("--all", action="store_true")
    sub.add_parser("stop", help="Drain the current cycle and prevent the next cycle")
    sub.add_parser("logs")
    sub.add_parser("install-skills", help="Install agent workflows in the host project")
    sub.add_parser("install-hooks")
    sub.add_parser("uninstall-hooks")
    sub.add_parser("message-state", help="Read a commit message from stdin and print its state")
    hook = sub.add_parser("hook")
    hook.add_argument("message", type=Path)
    state = sub.add_parser("state", help="Read the typed commit state")
    state.add_argument("ref", nargs="?", default="HEAD")
    skill = sub.add_parser("skill", help="Print the bundled operating instructions")
    skill.add_argument("name", choices=SKILLS)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--branch")
    status_parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            config = args.config.resolve() if args.config else Path.cwd() / "coloph-sync.toml"
            root = config.parent
            created = initialize(config)
            if args.json:
                print(
                    json.dumps(
                        {
                            "created": [str(path.relative_to(root)) for path in created],
                            "adoption_candidates": candidates(Git(root), "main") if (root / ".git").exists() else [],
                        }
                    )
                )
            else:
                for path in created:
                    print(f"Created {path.relative_to(root)}")
                if not created:
                    print("Project files are already initialized")
                print("Choose a delivery pattern and configure project commands before installing hooks")
                print("Then run: uv run coloph-sync install-hooks")
                if (root / ".git").exists():
                    message = hint(Git(root), "main")
                    if message:
                        print(message)
            return 0
        root = args.config.resolve().parent if args.config else Path.cwd()
        if args.command == "install-skills":
            created = install_skills(root)
            for path in created:
                print(f"Installed {path.relative_to(root)}")
            if not created:
                print("Agent workflows are already installed")
            return 0
        if args.command == "hook":
            config = load_config(args.config)
            return check(config, args.message.resolve())
        check_skills(root)
        if args.command == "message-state":
            state = read_state(sys.stdin.read())
            print(state.value if state else "unmarked")
            return 0
        if args.command == "skill":
            print(files("coloph_sync").joinpath("skills", args.name, "SKILL.md").read_text())
            return 0
        config = load_config(args.config)
        if args.command == "install-hooks":
            install(config)
            print("Installed commit-msg hook. Run: uv run coloph-sync init to install the agent workflows")
            message = hint(Git(root), config.main_ref)
            if message:
                print(message)
            return 0
        if args.command == "uninstall-hooks":
            uninstall(config)
            return 0
        engine = Engine(config)
        if args.command == "adopt":
            branches = candidates(engine.git, config.main_ref) if args.all else [args.branch]
            if not branches:
                print("No active worktree branches need adoption")
                return 0
            results = adopt(config, branches)
            for branch, error in results:
                print(f"Not adopted {branch}: {error}" if error else f"Adopted {branch}")
            return 2 if any(error for _, error in results) else 0
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
            branches = (
                engine.git.out("for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines()
                if args.all
                else [args.branch]
            )
            values = [status(engine, branch) for branch in branches]
            if args.json:
                print(json.dumps(values if args.all else values[0]))
            else:
                for value in values:
                    render(value)
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; reconcile any unfinished deploy attempt before resuming", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
