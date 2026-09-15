import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from coloph_install_skills.cli import main as install_skills

import coloph_sync.cli as cli
from coloph_sync.adoption import candidates, hint
from coloph_sync.cli import main, status
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


def test_status_tracks_current_branch_tip(project):
    config, git = project
    expected = commit(git, "new-tip")

    assert status(Engine(config))["commit"] == expected


def test_terminal_barrier_is_mergeable_after_parent_deploy(project, tmp_path):
    config, git = project
    child = tmp_path / "barrier-child"
    git.out("worktree", "add", "-b", "feature", str(child))
    branch = Git(child)
    parent = commit(branch, "before")
    branch.out("commit", "--allow-empty", "-m", "Boundary\n\nSync-State: deploy-barrier")
    barrier = branch.out("rev-parse", "HEAD")
    engine = Engine(config)
    engine.cycle()
    assert engine.deployed() == parent
    engine.cycle()
    assert engine.deployed() == barrier


def test_branch_filter_preserves_other_worktrees(project, tmp_path):
    config, git = project
    for name in ("allowed", "excluded"):
        path = tmp_path / name
        git.out("worktree", "add", "-b", name, str(path))
        commit(Git(path), name)
    engine = Engine(config)
    engine.branch = "allowed"
    engine.cycle()
    assert git.ancestor("allowed", "main")
    assert not git.ancestor("excluded", "main")


def test_dirty_worktree_is_skipped_until_clean(project, tmp_path):
    config, git = project
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "feature", str(child))
    branch = Git(child)
    commit(branch, "feature")
    (child / "uncommitted").write_text("uncommitted")

    engine = Engine(config)
    engine.merge_in()

    entry = engine.report["branches"]["feature"]
    assert not git.ancestor("feature", "main")
    assert entry["merge_status"] == "not_merged"
    assert entry["merge_reason"] == "worktree is dirty"
    assert entry["reason_code"] == "dirty"
    assert entry["last_merge_attempt"]["outcome"] == "skipped"

    (child / "uncommitted").unlink()
    engine.merge_in()

    assert git.ancestor("feature", "main")


def test_push_deploy_only_skips_merges_but_runs_integration_check(project, monkeypatch):
    config, _ = project
    engine = Engine(config)
    contexts = []
    monkeypatch.setattr(engine, "merge_in", lambda: pytest.fail("merge_in called"))
    monkeypatch.setattr(engine, "command", lambda command, context, **kwargs: contexts.append(context))
    monkeypatch.setattr(engine, "deploy", lambda sha: None)

    engine.cycle(push_deploy_only=True)

    assert contexts == ["integration"]


def test_disappearing_branch_is_reported_and_does_not_stop_other_merges(project, tmp_path, monkeypatch):
    config, git = project
    vanished = tmp_path / "vanished"
    remaining = tmp_path / "remaining"
    for name, path in (("vanished", vanished), ("remaining", remaining)):
        git.out("worktree", "add", "-b", name, str(path))
        commit(Git(path), name)
    engine = Engine(config)
    engine.report["branches"] = {"vanished": {"merge_status": "merged", "merge_reason": None}}
    worktrees = engine.git.worktrees

    def remove_vanished_after_discovery():
        discovered = worktrees()
        git.out("worktree", "remove", "--force", str(vanished))
        git.out("branch", "-D", "vanished")
        return discovered

    monkeypatch.setattr(engine.git, "worktrees", remove_vanished_after_discovery)
    engine.merge_in()

    entry = read_json(engine.report_path)["branches"]["vanished"]
    attempt = entry["last_merge_attempt"]
    assert attempt["outcome"] == "skipped"
    assert attempt["reason"] == "branch disappeared"
    assert entry["merge_status"] == "merged"
    assert git.ancestor("remaining", "main")


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
    git.out("config", "core.hooksPath", ".githooks")
    hook = config.root / ".githooks/commit-msg"
    hook.parent.mkdir()
    original = '#!/bin/sh\nprintf "\\nProject: checked\\n" >> "$1"\n'
    hook.write_text(original)
    hook.chmod(0o755)
    install(config)
    install(config)
    assert (hook.parent / "commit-msg.before-coloph-sync").read_text() == original
    assert 'root="$(git rev-parse --show-toplevel)"' in hook.read_text()
    assert 'exec uv run coloph-sync hook "$@"' in hook.read_text()
    uninstall(config)
    assert hook.read_text() == original


def test_installer_keeps_relative_version_controlled_hooks_path(project):
    config, git = project
    git.out("config", "core.hooksPath", ".githooks")

    install(config)

    hooks = (config.root / ".githooks").resolve()
    assert git.out("config", "--get", "core.hooksPath") == ".githooks"
    assert (hooks / "commit-msg").exists()


def test_installer_rejects_unversioned_hook_locations(project):
    config, git = project
    with pytest.raises(ValueError, match="init --install-hooks"):
        install(config)

    git.out("config", "core.hooksPath", str(git.common_dir() / "hooks"))
    with pytest.raises(ValueError, match="version-controlled project files"):
        install(config)


def test_hook_does_not_require_current_skills(project, monkeypatch):
    config, git = project
    message = git.root / "message"
    message.write_text("Change\n")
    monkeypatch.chdir(git.root)
    monkeypatch.setattr(cli, "load_config", lambda path: config)

    assert cli.main(["hook", str(message)]) == 0
    assert read_state(message.read_text()) == CommitState.PASSED


def test_skill_lifecycle_has_required_handoffs():
    root = Path(__file__).parents[1] / "src" / "coloph_sync" / "bundled_agent_skills"
    contributor = (root / "sync-contributor" / "SKILL.md").read_text()
    ship = (root / "sync-ship" / "SKILL.md").read_text()
    merge_main = (root / "sync-merge-main" / "SKILL.md").read_text()

    assert "immediately use `sync-ship` in the same turn" in contributor
    assert "Do not give a final user handoff from this workflow" in contributor
    assert "Do not report completion while work is only locally clean" in ship
    assert "it must continue through Step 5 production smoke, then\nStep 6 final executive summary" in ship
    assert "include the concise Step 6 handoff first" in ship
    assert "Return to `sync-ship` in the same turn" in merge_main
    assert (root / "sync-merge-main" / "references" / "conflict-review.md").exists()


def test_shared_installer_copies_complete_skills_and_creates_claude_links(tmp_path):
    assert install_skills(["--root", str(tmp_path)]) == 0
    assert install_skills(["--root", str(tmp_path), "--check"]) == 0
    assert (
        tmp_path / ".agents" / "skills" / "sync-merge-main" / "references" / "conflict-review.md"
    ).is_file()
    assert (tmp_path / ".claude" / "skills" / "sync-contributor").readlink() == Path(
        "../../.agents/skills/sync-contributor"
    )


def test_init_creates_config_and_skills_without_installing_hooks(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "coloph-sync.toml").exists()
    assert not (tmp_path / ".git").exists()
    assert "Choose a delivery pattern" in capsys.readouterr().out
    assert main(["--json", "init"]) == 0
    assert capsys.readouterr().out == '{"created": [], "adoption_candidates": [], "hooks_installed": false}\n'


def test_init_requires_explicit_hook_configuration(project, monkeypatch, capsys):
    config, git = project
    (config.root / "coloph-sync.toml").write_text('commit_check = ["true"]\ndeploy_command = ["true"]\n')
    monkeypatch.chdir(config.root)

    assert main(["init"]) == 2
    assert "init --install-hooks" in capsys.readouterr().err
    assert git.result("config", "--get", "core.hooksPath").returncode == 1

    assert main(["init", "--install-hooks"]) == 0
    assert "Installed commit-msg hook" in capsys.readouterr().out
    assert git.out("config", "--get", "core.hooksPath") == ".githooks"
    assert "# coloph-sync managed hook" in (config.root / ".githooks/commit-msg").read_text()


def test_init_uses_existing_version_controlled_hook_path(project, monkeypatch):
    config, git = project
    (config.root / "coloph-sync.toml").write_text('commit_check = ["true"]\ndeploy_command = ["true"]\n')
    git.out("config", "core.hooksPath", ".project-hooks")
    monkeypatch.chdir(config.root)

    assert main(["init"]) == 0
    assert git.out("config", "--get", "core.hooksPath") == ".project-hooks"
    assert (config.root / ".project-hooks/commit-msg").exists()


def test_init_warns_when_generated_hook_is_ignored(project, monkeypatch, capsys):
    config, git = project
    (config.root / "coloph-sync.toml").write_text('commit_check = ["true"]\ndeploy_command = ["true"]\n')
    (config.root / ".gitignore").write_text(".githooks/\n")
    monkeypatch.chdir(config.root)

    assert main(["init", "--install-hooks"]) == 0

    warning = capsys.readouterr().err
    assert ".gitignore:1:.githooks/" in warning
    assert "New worktrees will not receive it until it is unignored and committed" in warning
    assert (config.root / ".githooks/commit-msg").exists()


def test_new_worktree_receives_tracked_hook_without_setup(project, tmp_path, monkeypatch):
    config, git = project
    (config.root / "coloph-sync.toml").write_text('commit_check = ["true"]\ndeploy_command = ["true"]\n')
    monkeypatch.chdir(config.root)
    assert main(["init", "--install-hooks"]) == 0
    git.out("add", "coloph-sync.toml", ".githooks/commit-msg")
    git.out("commit", "-m", "Configure coloph-sync")

    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "feature", str(child))
    branch = Git(child)
    branch.out("commit", "--allow-empty", "-m", "Commit from new worktree")

    assert (child / ".githooks/commit-msg").exists()
    assert read_state(branch.message("HEAD")) == CommitState.PASSED


def test_install_reports_legacy_worktree_branches(project, tmp_path, monkeypatch, capsys):
    config, git = project
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "legacy", str(child))
    branch = Git(child)
    branch.out("commit", "--allow-empty", "-m", "Before coloph-sync")

    (config.root / "coloph-sync.toml").write_text('commit_check = ["true"]\ndeploy_command = ["true"]\n')
    monkeypatch.chdir(config.root)
    assert main(["init", "--install-hooks"]) == 0
    output = capsys.readouterr().out
    assert candidates(git, "main") == ["legacy"]
    assert "Existing worktree branches may need adoption: legacy" in output
    assert "uv run coloph-sync adopt --all" in output


def test_adoption_hint_truncates_branch_names(monkeypatch):
    monkeypatch.setattr("coloph_sync.adoption.candidates", lambda *_: [f"branch-{number}" for number in range(9)])

    output = hint(None, "main")

    assert "branch-7" in output
    assert "branch-8" not in output
    assert "and 1 more" in output


def test_adopt_checks_and_merges_a_legacy_branch(project, tmp_path, monkeypatch):
    config, git = project
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "legacy", str(child))
    branch = Git(child)
    branch.out("commit", "--allow-empty", "-m", "Before coloph-sync")
    legacy = branch.out("rev-parse", "HEAD")
    (config.root / "coloph-sync.toml").write_text('commit_check = ["true"]\ndeploy_command = ["true"]\n')
    git.out("add", "coloph-sync.toml")
    git.out("commit", "-m", "Configure coloph-sync")
    monkeypatch.chdir(config.root)
    assert main(["init", "--install-hooks"]) == 0
    git.out("add", ".githooks/commit-msg")
    git.out("commit", "-m", "Track commit hook")

    assert main(["adopt", "--all"]) == 0
    assert git.ancestor(legacy, "main")
    assert read_state(git.message("HEAD")) == CommitState.PASSED
    record = read_json(git.common_dir() / "coloph-sync-adoptions.json")["adoptions"][legacy]
    assert record["branch"] == "legacy"
    assert record["merged"] == git.resolve("main")
    assert candidates(git, "main") == []


def test_adopt_aborts_when_the_normal_merge_check_fails(project, tmp_path, monkeypatch):
    config, git = project
    child = tmp_path / "child"
    git.out("worktree", "add", "-b", "legacy", str(child))
    branch = Git(child)
    branch.out("commit", "--allow-empty", "-m", "Before coloph-sync")
    legacy = branch.out("rev-parse", "HEAD")
    command = [sys.executable, "-c", "raise SystemExit(1)"]
    (config.root / "coloph-sync.toml").write_text(
        f"commit_check = {json.dumps(command)}\ndeploy_command = [\"true\"]\n"
    )
    git.out("add", "coloph-sync.toml")
    git.out("commit", "-m", "Configure coloph-sync")
    monkeypatch.chdir(config.root)
    assert main(["init", "--install-hooks"]) == 0
    git.out("add", ".githooks/commit-msg")
    git.out("commit", "-m", "Track commit hook")

    assert main(["adopt", "--all"]) == 2
    assert not git.ancestor(legacy, "main")
    assert not git.resolve("MERGE_HEAD")
    assert not (git.common_dir() / "coloph-sync-adoptions.json").exists()


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


def test_pending_deploy_resumes_before_preflight(project, monkeypatch):
    config, git = project
    engine = Engine(replace(config, preflight_command=(sys.executable, "-c", "raise SystemExit(2)")))
    sha = git.out("rev-parse", "HEAD")
    write_json(engine.delivery_path, {"attempt": {"sha": sha, "status": "running"}})
    resumed = []
    monkeypatch.setattr(engine, "deploy", resumed.append)

    engine.cycle()

    assert resumed == [sha]


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


def test_config_requires_positive_live_output_limit(tmp_path):
    path = tmp_path / "coloph-sync.toml"
    path.write_text('commit_check = ["true"]\ndeploy_command = ["true"]\nlive_output_limit = 0\n')

    with pytest.raises(ValueError, match="live_output_limit"):
        load_config(path)


def test_command_bounds_live_output_and_keeps_complete_log(project, capsys):
    config, git = project
    command = (sys.executable, "-c", "print('first'); print('second'); print('third')")
    engine = Engine(replace(config, live_output_limit=8))

    engine.command(command, "integration")

    log = git.common_dir() / f"coloph-sync-{engine.run_id}.log"
    output = capsys.readouterr().out
    assert output.startswith(
        f"first\nse\nLive output truncated after 8 characters. Full log: {log}\nFinal output tail:\n"
    )
    assert output.endswith("first\nsecond\nthird\n")
    assert output.count("Live output truncated") == 1
    assert log.read_text().endswith("first\nsecond\nthird\n")


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
    install(config, configure=True)
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
    install(config, configure=True)
    engine = Engine(config)
    engine.merge_in()
    assert git.resolve("HEAD") == before
    assert not git.resolve("MERGE_HEAD")
    assert engine.report["branches"]["feature"]["merge_status"] == "not_merged"
