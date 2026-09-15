import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("deploy", Path(__file__).parents[1] / "scripts" / "deploy.py")
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


@pytest.fixture
def commands(monkeypatch):
    calls = []
    def run(*args, capture=False):
        calls.append(args)
        if args[:2] == ("git", "show"):
            return '[project]\nversion = "2.0.0"'
        if args[:2] == ("git", "ls-remote"):
            return "target\trefs/heads/main"
        if args[:2] == ("git", "rev-parse"):
            return "target"
        return ""
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", run)
    return calls


def test_unchanged_version_only_verifies(monkeypatch, commands):
    calls = commands
    current = "2.0.0"
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: "release")
    monkeypatch.setattr(deploy, "published_versions", lambda: {current})
    monkeypatch.setattr(deploy, "verify_published", lambda version: calls.append(("install", version)))

    deploy.main()

    assert not any(args[:3] == ("gh", "release", "create") for args in calls)
    assert ("install", current) in calls


def test_new_version_creates_release(monkeypatch, commands):
    calls = commands
    current = "2.0.0"
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: {"0.3.1"})
    monkeypatch.setattr(deploy, "ship_release", lambda tag: calls.append(("ship", tag)))

    deploy.main()

    release = next(args for args in calls if args[:3] == ("gh", "release", "create"))
    assert release[3:6] == (f"v{current}", "--target", "target")
    assert calls.index(("uv", "run", "python", "scripts/check.py")) < calls.index(release)
    assert calls.index(("python", "scripts/release.py", "build", "--tag", "v2.0.0")) < calls.index(release)
    assert ("ship", f"v{current}") in calls


def test_untagged_published_version_fails(monkeypatch, commands):
    current = "2.0.0"
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: {current})

    with pytest.raises(SystemExit, match="already contains untagged version"):
        deploy.main()


def test_old_target_never_uses_current_checkout_version(monkeypatch, commands):
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: "target")
    monkeypatch.setattr(deploy, "published_versions", lambda: set())
    shipped = []
    monkeypatch.setattr(deploy, "ship_release", shipped.append)
    deploy.main()
    assert shipped == ["v2.0.0"]
    assert not any(args[:3] == ("gh", "release", "create") for args in commands)


def test_checks_fail_before_tag_creation(monkeypatch, commands):
    original = deploy.run
    def fail(*args, **kwargs):
        if args == ("uv", "run", "python", "scripts/check.py"):
            raise RuntimeError("stale installed skills")
        return original(*args, **kwargs)
    monkeypatch.setattr(deploy, "run", fail)
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: set())
    with pytest.raises(RuntimeError, match="stale"):
        deploy.main()
    assert not any(args[:3] == ("gh", "release", "create") for args in commands)


@pytest.mark.parametrize("state,publisher,expected", [
    ("completed", "skipped", "replace"),
    ("completed", "failure", "blocked"),
    ("completed", "success", "blocked"),
    ("in_progress", "skipped", "retry"),
])
def test_replacement_requires_terminal_unpublished_evidence(monkeypatch, commands, state, publisher, expected):
    original = deploy.run
    def run(*args, **kwargs):
        if args[:3] == ("gh", "run", "list"):
            return json.dumps([{"databaseId": 1, "status": state, "headSha": "target"}])
        if args[:3] == ("gh", "run", "view"):
            return json.dumps({"jobs": [{"name": "publish", "conclusion": publisher}]})
        return original(*args, **kwargs)
    monkeypatch.setattr(deploy, "run", run)
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: "target")
    monkeypatch.setattr(deploy, "published_versions", lambda: set())
    assert deploy.reconcile("target")["outcome"] == expected


def test_wait_for_install_retries_until_uv_can_install(monkeypatch):
    results = iter((SimpleNamespace(returncode=1, stderr="not found"), SimpleNamespace(returncode=0, stderr="")))
    sleeps = []
    monkeypatch.setattr(deploy, "install_published", lambda version: next(results))
    monkeypatch.setattr(deploy.time, "time", lambda: 0)
    monkeypatch.setattr(deploy.time, "sleep", sleeps.append)

    deploy.wait_for_install("0.3.3")

    assert sleeps == [deploy.INSTALL_INTERVAL]


def test_partial_publication_is_not_success(monkeypatch):
    response = {"info": {"version": "2.0.0"}, "urls": [{"filename": "coloph_sync-2.0.0-py3-none-any.whl"}]}
    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda *args, **kwargs: io.StringIO(json.dumps(response)))
    with pytest.raises(SystemExit, match="incomplete"):
        deploy.verify_published("2.0.0")
