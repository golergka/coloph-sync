#!/usr/bin/env python3
import argparse
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def run(*command, cwd=ROOT):
    subprocess.run(command, cwd=cwd, check=True)


def version():
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def artifacts():
    current = version()
    paths = [*DIST.glob(f"coloph_sync-{current}-*.whl"), *DIST.glob(f"coloph_sync-{current}.tar.gz")]
    if len(paths) != 2:
        raise SystemExit(f"expected one wheel and one source distribution for {current}")
    return paths


def check_tag(tag):
    if tag and tag != f"v{version()}":
        raise SystemExit(f"release tag {tag!r} does not match package version v{version()}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "publish"))
    parser.add_argument("--tag")
    args = parser.parse_args()
    check_tag(args.tag)
    if args.command == "build":
        run("uv", "build", "--no-sources")
        for artifact in artifacts():
            with tempfile.TemporaryDirectory() as directory:
                run(
                    "uv",
                    "run",
                    "--isolated",
                    "--no-project",
                    "--no-cache",
                    "--with",
                    str(artifact),
                    "coloph-sync",
                    "init",
                    cwd=Path(directory),
                )
                assert (Path(directory) / "coloph-sync.toml").exists()
                run("uv", "run", "--with", str(artifact), "coloph-install-skills", cwd=Path(directory))
                assert len(list((Path(directory) / ".agents" / "skills").glob("*/SKILL.md"))) == 6
                assert len(list((Path(directory) / ".claude" / "skills").iterdir())) == 6
                assert (
                    Path(directory) / ".agents" / "skills" / "sync-merge-main" / "references" / "conflict-review.md"
                ).is_file()
    else:
        run("uv", "publish", *(str(path) for path in artifacts()))


if __name__ == "__main__":
    main()
