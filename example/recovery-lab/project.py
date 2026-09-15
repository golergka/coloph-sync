"""Project-owned checks and a local publication service for recovery exercises."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT.parent / "service"


def target_settings(target):
    return json.loads(subprocess.check_output(["git", "show", f"{target}:settings.json"], text=True))


def main():
    command = sys.argv[1]
    local = json.loads((ROOT / "settings.json").read_text())
    if command == "check":
        if os.environ.get("COLOPH_SYNC_CONTEXT") == "integration":
            assert local["message"] == "Hello", "The delivered page must say Hello"
        return
    target = os.environ["COLOPH_SYNC_COMMIT"]
    record = STATE / f"{target}.json"
    settings = target_settings(target)
    previous = json.loads(record.read_text()) if record.exists() else {}
    if command == "reconcile":
        if previous.get("status") == "published":
            outcome, reason = "delivered", "The local service contains the exact target"
        elif previous.get("status") == "failed":
            outcome, reason = "replace", "The service rejected the payload before publication; no operation remains active"
        else:
            outcome, reason = "retry", "No publication exists for this target"
        print(json.dumps({"outcome": outcome, "reason": reason}))
        return
    if previous.get("status") == "published":
        return
    # This value belongs to tooling. Repairs can change it without changing the target payload.
    assert local["builder"] == "builtin", "Unknown builder; this project supports builtin"
    STATE.mkdir(exist_ok=True)
    if settings["payload"] != "valid":
        record.write_text(json.dumps({"status": "failed", "target": target}))
        raise SystemExit("The immutable release payload is invalid")
    record.write_text(json.dumps({"status": "published", "target": target, "message": settings["message"]}))
    with (STATE / "publications.log").open("a") as stream:
        stream.write(target + "\n")
    if local["lose_ack"]:
        raise SystemExit("Connection closed after publication")


if __name__ == "__main__":
    main()
