import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("deploy", Path(__file__).parents[1] / "scripts" / "deploy.py")
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


def test_unchanged_version_only_verifies(monkeypatch):
    calls = []
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", lambda *args, **kwargs: calls.append(args) or "target\trefs/heads/main")
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: "release")
    monkeypatch.setattr(deploy, "published_versions", lambda: {"0.3.2"})

    deploy.main()

    assert not any(args[:3] == ("gh", "release", "create") for args in calls)


def test_new_version_creates_release(monkeypatch):
    calls = []
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", lambda *args, **kwargs: calls.append(args) or "target\trefs/heads/main")
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: {"0.3.1"})
    monkeypatch.setattr(deploy, "finish_release", lambda tag: calls.append(("finish", tag)))

    deploy.main()

    assert ("gh", "release", "create", "v0.3.2", "--target", "target", "--title", "v0.3.2", "--generate-notes") in calls
    assert ("finish", "v0.3.2") in calls


def test_untagged_published_version_fails(monkeypatch):
    monkeypatch.setenv("COLOPH_SYNC_COMMIT", "target")
    monkeypatch.setattr(deploy, "run", lambda *args, **kwargs: "target\trefs/heads/main")
    monkeypatch.setattr(deploy, "remote_tag", lambda tag: None)
    monkeypatch.setattr(deploy, "published_versions", lambda: {"0.3.2"})

    with pytest.raises(SystemExit, match="already contains untagged version"):
        deploy.main()
