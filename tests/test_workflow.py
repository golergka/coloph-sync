import json
import subprocess
import sys
from dataclasses import replace

import pytest

from coloph_sync.cli import status
from coloph_sync.config import Config, load_config
from coloph_sync.engine import Engine
from coloph_sync.git import Git
from coloph_sync.hooks import check, install, uninstall
from coloph_sync.state import CommitState, read_state, write_state
from coloph_sync.storage import read_json, write_json


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    git = Git(root)
    git.out("init", "-b", "main")
    git.out("config", "user.name", "Test")
    git.out("config", "user.email", "test@example.com")
    git.out("commit", "--allow-empty", "-m", "Initial\n\nSync-State: passed")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git.out("remote", "add", "origin", str(remote))
    git.out("push", "-u", "origin", "main")
    command = (sys.executable, "-c", "pass")
    config = Config(root, command, command)
    return config, git


def commit(git, name, state="passed"):
    (git.root / name).write_text(name)
    git.out("add", name)
    git.out("commit", "-m", f"{name}\n\nSync-State: {state}")
    return git.out("rev-parse", "HEAD")


@pytest.mark.parametrize("state", list(CommitState))
def test_state_round_trip(state):
    assert read_state(write_state("A subject\n\nDetails", state)) == state


def test_state_rejects_combinations():
    with pytest.raises(ValueError):
        read_state("Subject\n\nSync-State: passed\nSync-State: wip")


def test_status_exposes_failed_integration_after_deployment(project):
    config, git = project
    engine = Engine(config)
    engine.deploy(git.out("rev-parse", "HEAD"))
    engine.report["checks_status"] = "failed"
    engine.save()
    result = status(engine)
    assert result["deployed"]
    assert result["checks"] == "failed"
    assert result["verdict"] == "action needed"


@pytest.mark.parametrize("code,state,hook_code", [(0, "passed", 0), (1, "failed", 0), (2, None, 1), (7, None, 1)])
def test_check_outcomes(project, code, state, hook_code):
    config, git = project
    message = git.common_dir() / "test-message"
    message.write_text("Change\n")
    config = replace(config, commit_check=(sys.executable, "-c", f"print('diagnostic'); raise SystemExit({code})"))
    assert check(config, message) == hook_code
    assert read_state(message.read_text()) == state
    assert read_json(git.common_dir() / "coloph-sync-check.json")["output"] == "diagnostic\n"


def test_scaffold_and_empty_barrier(project):
    config, git = project
    message = git.common_dir() / "message"
    message.write_text("Scaffold\n\nSync-State: dont-merge")
    assert check(config, message) == 0
    assert read_state(message.read_text()) == CommitState.DONT_MERGE
    (git.root / "file").write_text("x")
    git.out("add", "file")
    message.write_text("Boundary\n\nSync-State: deploy-barrier")
    with pytest.raises(ValueError, match="empty"):
        check(config, message)


def test_installer_preserves_existing_hook(project):
    config, git = project
    hook = git.common_dir() / "hooks/commit-msg"
    original = '#!/bin/sh\nprintf "\\nProject: checked\\n" >> "$1"\n'
    hook.write_text(original)
    hook.chmod(0o755)
    install(config)
    install(config)
    assert (hook.parent / "commit-msg.before-coloph-sync").read_text() == original
    uninstall(config)
    assert hook.read_text() == original


def test_barrier_releases_only_after_deployment(project, tmp_path):
    config, git = project
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "feature", str(child))
    branch = Git(child)
    first = commit(branch, "first")
    branch.out("commit", "--allow-empty", "-m", "Boundary\n\nSync-State: deploy-barrier")
    last = commit(branch, "last")
    engine = Engine(config)
    engine.cycle()
    assert git.ancestor(first, "main")
    assert not git.ancestor(last, "main")
    assert engine.deployed() == first
    engine.cycle()
    assert git.ancestor(last, "main")
    assert engine.deployed() == last


def test_conflict_isolated_and_cached(project, tmp_path):
    config, git = project
    commit(git, "shared")
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "feature", str(child))
    branch = Git(child)
    (child / "shared").write_text("branch")
    branch.out("commit", "-am", "Branch\n\nSync-State: passed")
    (git.root / "shared").write_text("main")
    git.out("commit", "-am", "Main\n\nSync-State: passed")
    engine = Engine(config)
    engine.merge_in()
    entry = engine.report["branches"]["feature"]
    assert entry["reason_code"] == "conflict"
    assert not git.resolve("MERGE_HEAD")
    engine.merge_in()
    assert entry != engine.report["branches"]["feature"]
    assert engine.report["branches"]["feature"]["last_merge_attempt"]["outcome"] == "unchanged"


def test_publication_retry_does_not_deploy_twice(project, monkeypatch):
    config, git = project
    counter = git.common_dir() / "count"
    command = (
        sys.executable,
        "-c",
        f"from pathlib import Path; p=Path({str(counter)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x')",
    )
    engine = Engine(replace(config, deploy_command=command))
    sha = git.out("rev-parse", "HEAD")
    publish = engine.publish
    monkeypatch.setattr(engine, "publish", lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        engine.deploy(sha)
    assert read_json(engine.delivery_path)["attempt"]["status"] == "completed"
    assert engine.deployed() == sha
    monkeypatch.setattr(engine, "publish", publish)
    engine.deploy(sha)
    assert counter.read_text() == "x"
    assert engine.deployed() == sha


def test_failed_deploy_reuses_identity_before_new_work(project):
    config, git = project
    engine = Engine(replace(config, deploy_command=(sys.executable, "-c", "raise SystemExit(2)")))
    sha = git.out("rev-parse", "HEAD")
    with pytest.raises(subprocess.CalledProcessError):
        engine.deploy(sha)
    attempt = read_json(engine.delivery_path)["attempt"]["id"]
    engine.config = config
    engine.cycle()
    assert read_json(engine.delivery_path)["attempt"]["id"] == attempt


def test_concurrent_publication_does_not_overwrite(project):
    config, git = project
    engine = Engine(config)
    first = git.out("rev-parse", "HEAD")
    second = commit(git, "second")
    git.out("push", "origin", "main")
    git.out("push", "origin", f"{second}:refs/tags/deployed")
    delivery = {"attempt": {"id": "test", "sha": first, "status": "completed", "previous_remote": None}}
    with pytest.raises(RuntimeError, match="concurrently"):
        engine.publish(delivery)
    assert engine.remote_ref("refs/tags/deployed") == second


def test_config_requires_deployment(tmp_path):
    path = tmp_path / "coloph-sync.toml"
    path.write_text('commit_check = ["true"]\n')
    with pytest.raises(ValueError, match="deploy_command"):
        load_config(path)


def test_stop_drains_owned_cycle(project, monkeypatch):
    config, git = project
    engine = Engine(config)
    calls = []

    def cycle(**kwargs):
        calls.append("cycle")
        write_json(engine.stop_path, read_json(engine.owner_path))
        calls.append("completed")

    monkeypatch.setattr(engine, "cycle", cycle)
    engine.run()
    assert calls == ["cycle", "completed"]
    assert not engine.owner_path.exists()


def test_real_git_hook_and_saved_failure(project):
    config, git = project
    path = config.root / "coloph-sync.toml"
    command = [sys.executable, "-c", "print('negative verdict'); raise SystemExit(1)"]
    path.write_text(
        f"commit_check = {json.dumps(command)}\ndeploy_command = {json.dumps([sys.executable, '-c', 'pass'])}\n"
    )
    git.out("add", "coloph-sync.toml")
    git.out("commit", "-m", "Configure\n\nSync-State: passed")
    install(config)
    git.out("commit", "--allow-empty", "-m", "Review this")
    assert read_state(git.message("HEAD")) == CommitState.FAILED
    assert "Review this" == git.message("HEAD").splitlines()[0]


def test_real_merge_hook_rejects_automatic_negative_verdict(project, tmp_path):
    config, git = project
    command = [sys.executable, "-c", "raise SystemExit(1)"]
    path = config.root / "coloph-sync.toml"
    path.write_text(
        f"commit_check = {json.dumps(command)}\ndeploy_command = {json.dumps([sys.executable, '-c', 'pass'])}\n"
    )
    git.out("add", "coloph-sync.toml")
    git.out("commit", "-m", "Configure\n\nSync-State: passed")
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "feature", str(child))
    commit(Git(child), "feature")
    before = commit(git, "main-file")
    install(config)
    engine = Engine(config)
    engine.merge_in()
    assert git.resolve("HEAD") == before
    assert not git.resolve("MERGE_HEAD")
    assert engine.report["branches"]["feature"]["merge_status"] == "not_merged"
