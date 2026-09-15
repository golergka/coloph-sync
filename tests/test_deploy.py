import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("deploy", Path(__file__).parents[1] / "scripts" / "deploy.py")
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


def test_unchanged_version_only_verifies(monkeypatch):
    calls = []
    current, _ = deploy.version()
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", lambda *args, **kwargs: calls.append(args) or "target\trefs/heads/main")
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: "release")
    monkeypatch.setattr(deploy, "published_versions", lambda: {current})
    monkeypatch.setattr(deploy, "wait_for_install", lambda version: calls.append(("install", version)))

    deploy.main()

    assert not any(args[:3] == ("gh", "release", "create") for args in calls)
    assert ("install", current) in calls


def test_new_version_creates_release(monkeypatch):
    calls = []
    current, _ = deploy.version()
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", lambda *args, **kwargs: calls.append(args) or "target\trefs/heads/main")
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: {"0.3.1"})
    monkeypatch.setattr(deploy, "ship_release", lambda tag: calls.append(("ship", tag)))

    deploy.main()

    assert ("gh", "release", "create", f"v{current}", "--target", "target", "--title", f"v{current}", "--generate-notes") in calls
    assert ("ship", f"v{current}") in calls


def test_untagged_published_version_fails(monkeypatch):
    current, _ = deploy.version()
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", lambda *args, **kwargs: "target\trefs/heads/main")
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: {current})

    with pytest.raises(SystemExit, match="already contains untagged version"):
        deploy.main()


def test_wait_for_install_retries_until_uv_can_install(monkeypatch):
    results = iter((SimpleNamespace(returncode=1, stderr="not found"), SimpleNamespace(returncode=0, stderr="")))
    sleeps = []
    monkeypatch.setattr(deploy, "install_published", lambda version: next(results))
    monkeypatch.setattr(deploy.time, "time", lambda: 0)
    monkeypatch.setattr(deploy.time, "sleep", sleeps.append)

    deploy.wait_for_install("0.3.3")

    assert sleeps == [deploy.INSTALL_INTERVAL]
