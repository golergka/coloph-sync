#!/usr/bin/env python3
import os
import subprocess

environment = os.environ.copy()
local_names = subprocess.run(
    ("git", "rev-parse", "--local-env-vars"), check=True, text=True, capture_output=True
).stdout.splitlines()
for name in local_names:
    environment.pop(name, None)

for command in (
    ("uv", "lock", "--check"),
    ("uv", "run", "coloph-install-skills", "--check"),
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "pytest", "-q"),
):
    subprocess.run(command, check=True, env=environment)
