"""Exercise seeded failures with the real CLI, hooks, local service, and remote."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "recovery_lab", Path(__file__).parents[1] / "example/recovery-lab/create.py"
)
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


@pytest.mark.parametrize("scenario", lab.SCENARIOS)
def test_seeded_failure_recovers_through_normal_workflow(tmp_path, scenario):
    project = lab.create(tmp_path / scenario, scenario)

    def run(*args):
        return subprocess.check_output(args, cwd=project, text=True)

    original = run("git", "rev-parse", "HEAD").strip()
    if scenario in ("integration", "deploy-tool", "immutable-payload"):
        path = project / "settings.json"
        settings = json.loads(path.read_text())
        settings.update(message="Hello", builder="builtin", payload="valid")
        path.write_text(json.dumps(settings, indent=2) + "\n")
        run("git", "add", "settings.json")
        run("git", "commit", "-m", "Repair project behavior")
    run("uv", "run", "coloph-sync", "run", "--once")
    status = json.loads(run("uv", "run", "coloph-sync", "--json", "status"))
    assert status["merged"] and status["deployed"]
    assert status["pending_deployment"] is None
    head = run("git", "rev-parse", "HEAD").strip()
    service = project.parent / "service"
    result = json.loads((service / f"{head}.json").read_text())
    assert result == {"status": "published", "target": head, "message": "Hello"}
    publications = (service / "publications.log").read_text().splitlines()
    assert len(publications) == len(set(publications))
    assert len(publications) == 1
    if scenario == "immutable-payload":
        history = json.loads((project / ".git/coloph-sync-delivery.json").read_text())["history"]
        assert history[0]["sha"] == original
        assert history[0]["status"] == "superseded"
        assert json.loads((service / f"{original}.json").read_text())["status"] == "failed"
    assert not run("git", "status", "--porcelain").strip()


def test_web_example_rejects_mixed_commits(tmp_path):
    project = tmp_path / "site"
    project.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=project, text=True).strip()
    git("init", "-b", "main")
    git("config", "user.name", "Example test")
    git("config", "user.email", "example@example.invalid")
    (project / "public").mkdir()
    page = project / "public/index.html"
    page.write_text("old payload")
    git("add", ".")
    git("commit", "-m", "Initial")
    target = git("rev-parse", "HEAD")
    page.write_text("new payload")
    git("commit", "-am", "Later work")
    root = tmp_path / "web-root"
    script = Path(__file__).parents[1] / "example/continuous-web-app/scripts/deploy"
    environment = {**os.environ, "WEB_ROOT": str(root), "COLOPH_SYNC_COMMIT": target}
    result = subprocess.run([sys.executable, str(script)], cwd=project, env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert not root.exists()
    environment["COLOPH_SYNC_COMMIT"] = git("rev-parse", "HEAD")
    for _ in range(2):
        subprocess.run([sys.executable, str(script)], cwd=project, env=environment, check=True)
        assert (root / "current/index.html").read_text() == "new payload"
