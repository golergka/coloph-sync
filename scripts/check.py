#!/usr/bin/env python3
import subprocess

for command in (
    ("uv", "lock", "--check"),
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "pytest", "-q"),
):
    subprocess.run(command, check=True)
