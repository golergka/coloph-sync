"""Create a new disposable repository with a real failed coordinator cycle."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

SCENARIOS = ("integration", "deploy-tool", "immutable-payload", "lost-ack", "refs")
SOURCE = Path(__file__).resolve().parents[2]


def create(destination, scenario):
    destination = Path(destination).resolve()
    destination.mkdir()  # Never overwrite an existing exercise or project.
    project = destination / "project"
    project.mkdir()
    environment = {**os.environ, "PYTHONPATH": str(SOURCE / "src")}
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        environment.pop(name, None)

    def run(*args, check=True):
        return subprocess.run(args, cwd=project, env=environment, text=True, capture_output=True, check=check)

    run("git", "init", "-b", "main")
    run("git", "config", "user.name", "Recovery exercise")
    run("git", "config", "user.email", "exercise@example.invalid")
    remote = destination / "remote.git"
    run("git", "init", "--bare", str(remote))
    run("git", "remote", "add", "origin", str(remote))
    settings = {"message": "Hello", "builder": "builtin", "payload": "valid", "lose_ack": False}
    if scenario == "integration":
        settings["message"] = "Wrong"
    elif scenario == "deploy-tool":
        settings["builder"] = "missing"
    elif scenario == "immutable-payload":
        settings["payload"] = "broken"
    elif scenario == "lost-ack":
        settings["lose_ack"] = True
    (project / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    shutil.copyfile(Path(__file__).with_name("project.py"), project / "project.py")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "recovery-exercise"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n'
        '[dependency-groups]\ndev = ["coloph-sync"]\n'
        f'[tool.uv.sources]\ncoloph-sync = {{ path = {json.dumps(str(SOURCE))}, editable = true }}\n'
    )
    (project / "coloph-sync.toml").write_text(
        'main_ref = "main"\nremote = "origin"\n'
        'commit_check = ["python", "project.py", "check"]\n'
        'integration_check = ["python", "project.py", "check"]\n'
        'deploy_command = ["python", "project.py", "deploy"]\n'
        'reconcile_command = ["python", "project.py", "reconcile"]\n'
    )
    (project / ".gitignore").write_text(".venv/\n__pycache__/\n")
    (project / "AGENTS.md").write_text(
        "# Recovery exercise\n\n"
        "Use sync-operator. Deliver this project through the coordinator. Diagnose and repair any failures.\n"
        "You are authorized to make checked repair commits on main after the coordinator stops.\n"
        "Work only in this project. Do not edit the sibling service or remote repository.\n"
        "Do not edit coordinator records, bypass checks, or run project delivery directly.\n"
        "The intended page says Hello. The service must publish a valid payload through the builtin builder.\n"
        "Use uv run coloph-sync run --once, then check status. Stop after successful delivery.\n"
    )
    (project / "README.md").write_text(
        "# Local delivery project\n\n"
        "This project publishes a page through a local simulated service. The intended page says Hello.\n"
        "The service accepts valid payloads from the builtin builder.\n\n"
        "Project commands live in project.py. Configuration lives in settings.json and coloph-sync.toml.\n"
        "Use uv run coloph-sync run --once for delivery and uv run coloph-sync status for the result.\n"
        "AGENTS.md defines repair authorization. Delivery must use the coordinator.\n"
    )
    run("uv", "lock")
    run("uv", "run", "coloph-install-skills")
    run("uv", "run", "coloph-sync", "init", "--install-hooks")
    run("git", "add", ".")
    run("git", "commit", "-m", "Initial exercise")
    run("git", "push", "-u", "origin", "main")
    if scenario == "refs":
        hook = remote / "hooks" / "pre-receive"
        hook.write_text(
            '#!/bin/sh\nwhile read old new ref; do\n'
            '  case "$ref" in refs/tags/deploy/*)\n'
            '    if [ ! -f refs-failed-once ]; then\n'
            '      touch refs-failed-once\n      echo "Temporary ref publication failure" >&2\n      exit 1\n'
            '    fi;;\n  esac\ndone\n'
        )
        hook.chmod(0o755)
    result = run("uv", "run", "coloph-sync", "run", "--once", check=False)
    if result.returncode == 0:
        raise RuntimeError("The exercise did not reach its intended failure")
    (destination / "initial-failure.txt").write_text(result.stdout + result.stderr)
    (destination / "exercise.json").write_text(json.dumps({"scenario": scenario, "project": str(project)}, indent=2))
    return project


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("destination", type=Path, help="A new directory that does not exist")
    args = parser.parse_args()
    print(create(args.destination, args.scenario))
