"""TOML configuration, following the coloph-migrations configuration layout."""

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    root: Path
    commit_check: tuple[str, ...]
    deploy_command: tuple[str, ...]
    merge_check: tuple[str, ...] = ()
    integration_check: tuple[str, ...] = ()
    preflight_command: tuple[str, ...] = ()
    main_ref: str = "main"
    remote: str = "origin"
    deployed_ref: str = "deployed"
    deploy_tag_prefix: str = "deploy"
    check_timeout: int = 14400
    deploy_timeout: int = 14400
    merge_timeout: int = 1500
    interval: int = 60


def load_config(path: Path | None = None) -> Config:
    path = path.resolve() if path else Path.cwd() / "coloph-sync.toml"
    root = path.parent
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    local = root / "coloph-sync.local.toml"
    if local.exists() and local != path:
        with local.open("rb") as stream:
            raw.update(tomllib.load(stream))
    unknown = set(raw) - {field.name for field in fields(Config) if field.name != "root"}
    if unknown:
        raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
    for name in ("commit_check", "merge_check", "integration_check", "deploy_command", "preflight_command"):
        value = raw.get(name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ValueError(f"{name} must be an argument array")
        if name in ("commit_check", "deploy_command") and not value:
            raise ValueError(f"{name} is required")
        raw[name] = tuple(value)
    for name in ("check_timeout", "deploy_timeout", "merge_timeout", "interval"):
        if name in raw and (type(raw[name]) is not int or raw[name] <= 0):
            raise ValueError(f"{name} must be a positive integer")
    for name in ("main_ref", "remote", "deployed_ref", "deploy_tag_prefix"):
        if name in raw and (not isinstance(raw[name], str) or not raw[name] or raw[name].startswith("-")):
            raise ValueError(f"Invalid {name}")
    return Config(root=root, **raw)
