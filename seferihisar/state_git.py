"""Durable SQLite state on an isolated Git branch, never on the code branch.

Uses the checkout's existing Git authentication, not credentials in scripts.
Missing branch is a valid first run; other remote failures stop the pipeline.
"""
from __future__ import annotations

import argparse
import base64
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from .security import validate_state

BRANCH = "automation-state"


def git(*args: str, input: bytes | None = None) -> bytes:
    env = os.environ.copy()
    if token := env.get("STATE_WRITE_TOKEN"):
        # Scoped to this Git child process; never written to .git/config or argv.
        index = int(env.get("GIT_CONFIG_COUNT", "0"))
        env["GIT_CONFIG_COUNT"] = str(index + 1)
        env[f"GIT_CONFIG_KEY_{index}"] = "http.https://github.com/.extraheader"
        credential = base64.b64encode(("x-access-token:" + token).encode()).decode()
        env[f"GIT_CONFIG_VALUE_{index}"] = "AUTHORIZATION: basic " + credential
    return subprocess.run(["git", *args], input=input, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def remote_head() -> str | None:
    result = git("ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}").decode().strip()
    if not result:
        return None
    git("fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}")
    return result.split()[0]


def restore(path: Path):
    head = remote_head()
    path.parent.mkdir(parents=True, exist_ok=True)
    if head:
        path.write_bytes(git("show", f"{head}:platform.sqlite"))
        db = sqlite3.connect(path)
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Stored state failed integrity validation")
        finally:
            db.close()
        validate_state(path)


def persist(path: Path):
    if not path.exists():
        raise RuntimeError("State database missing; refusing to overwrite remote state")
    validate_state(path)
    head = remote_head()
    # sqlite.backup produces a consistent image without WAL/journal loss.
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "platform.sqlite"
        source = sqlite3.connect(path)
        target = sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        blob = git("hash-object", "-w", "--stdin", input=backup.read_bytes()).decode().strip()
    tree = git("mktree", input=f"100644 blob {blob}\tplatform.sqlite\n".encode()).decode().strip()
    if head and git("rev-parse", f"{head}^{{tree}}").decode().strip() == tree:
        return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    args = ["commit-tree", tree, "-m", "Persist public-safe automation state"]
    if head:
        args += ["-p", head]
    commit = git(*args).decode().strip()
    # Explicit lease refuses concurrent writes instead of dropping somebody's updates.
    git("push", f"--force-with-lease=refs/heads/{BRANCH}:{head or ''}", "origin", f"{commit}:refs/heads/{BRANCH}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("restore", "persist"))
    parser.add_argument("--db", type=Path, default=Path("state/platform.sqlite"))
    args = parser.parse_args()
    try:
        (restore if args.action == "restore" else persist)(args.db)
    except (subprocess.CalledProcessError, sqlite3.Error, RuntimeError, ValueError):
        # Git diagnostics may carry auth URLs. Do not print them in public logs.
        raise SystemExit("Durable state operation failed; state was not reset. Check repository write permissions and automation-state branch.") from None


if __name__ == "__main__":
    main()
