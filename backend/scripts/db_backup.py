"""Manual tool: back up the database, and prove a backup restores. Not part of the app.

`backup` writes a compressed dump (pg_dump custom format) plus a db_verify fingerprint taken right
after it, into backend/logs/backups/ (git-ignored), and keeps only the newest --keep dumps.
`restore-check` restores a dump into a throwaway database on the same server, fingerprints it,
compares that with the fingerprint saved at backup time, and drops the throwaway database. Exit
code 0 means the backup is good. The app keeps writing (api_usage, jobs) while a backup runs, so
run the check while the app is idle, or expect differences only in those log tables.

By default pg_dump / pg_restore run inside the local Postgres container (none are installed on the
host). With --local they run from the host's PATH against DATABASE_URL instead, which is what a
hosted database needs (install the Postgres client tools of the same major version, 16).

Usage (from backend/, venv active):
    python scripts/db_backup.py backup                        # local container, keep 14
    python scripts/db_backup.py backup --keep 30
    python scripts/db_backup.py restore-check logs/backups/sales_intel_20261120_101500.dump
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_DIR = BACKEND / "logs" / "backups"
DEFAULT_CONTAINER = "infra-postgres-pgvector-1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help="Postgres container")
    parser.add_argument(
        "--local", action="store_true", help="use pg_dump/pg_restore from PATH, not the container"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="dump the database and fingerprint it")
    backup.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    backup.add_argument("--keep", type=int, default=14, help="how many dumps to keep")
    check = sub.add_parser("restore-check", help="restore a dump into a scratch database")
    check.add_argument("dump", type=Path)
    return parser.parse_args()


def _run(args: list[str], env: dict[str, str] | None = None) -> None:
    print("  $ " + " ".join(args))
    subprocess.run(args, check=True, env=env)


def _libpq_env(url: str) -> dict[str, str]:
    """Connection settings for the Postgres command-line tools, from a SQLAlchemy URL."""
    u = make_url(url)
    env = dict(os.environ)
    env.update(
        {
            "PGHOST": u.host or "localhost",
            "PGPORT": str(u.port or 5432),
            "PGUSER": u.username or "",
            "PGPASSWORD": u.password or "",
        }
    )
    return env


def _verify(args: list[str]) -> int:
    return subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "db_verify.py"), *args], check=False
    ).returncode


def backup(opts: argparse.Namespace) -> int:
    url = get_settings().database_url
    db = make_url(url).database or ""
    opts.dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dump = opts.dir / f"{db}_{stamp}.dump"
    if opts.local:
        _run(["pg_dump", "-Fc", "-d", db, "-f", str(dump)], env=_libpq_env(url))
    else:
        inside = f"/tmp/{dump.name}"
        user = make_url(url).username or "postgres"
        _run(
            ["docker", "exec", opts.container, "pg_dump", "-U", user, "-d", db, "-Fc", "-f", inside]
        )
        _run(["docker", "cp", f"{opts.container}:{inside}", str(dump)])
        _run(["docker", "exec", opts.container, "rm", "-f", inside])
    if dump.stat().st_size == 0:
        print(f"FAIL: {dump} is empty")
        return 1
    if _verify(["snapshot", "--out", str(dump.with_suffix(".json"))]) != 0:
        return 1

    dumps = sorted(opts.dir.glob(f"{db}_*.dump"))
    for old in dumps[: max(0, len(dumps) - opts.keep)]:
        old.unlink()
        old.with_suffix(".json").unlink(missing_ok=True)
        print(f"  removed old backup {old.name}")
    print(f"\nBackup written: {dump} ({dump.stat().st_size:,} bytes)")
    return 0


def restore_check(opts: argparse.Namespace) -> int:
    dump: Path = opts.dump
    fingerprint = dump.with_suffix(".json")
    if not dump.exists() or not fingerprint.exists():
        print(f"FAIL: need both {dump} and {fingerprint}")
        return 1
    url = get_settings().database_url
    u = make_url(url)
    scratch = f"{u.database}_restore_check"
    scratch_url = u.set(database=scratch).render_as_string(hide_password=False)
    drop = f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'
    create = f'CREATE DATABASE "{scratch}"'

    if opts.local:
        env = _libpq_env(url)
        for sql in (drop, create):
            _run(["psql", "-d", "postgres", "-c", sql], env=env)
        _run(["pg_restore", "--no-owner", "--exit-on-error", "-d", scratch, str(dump)], env=env)
    else:
        user = u.username or "postgres"
        exec_ = ["docker", "exec", opts.container]
        for sql in (drop, create):
            _run([*exec_, "psql", "-U", user, "-d", "postgres", "-c", sql])
        inside = f"/tmp/{dump.name}"
        _run(["docker", "cp", str(dump), f"{opts.container}:{inside}"])
        _run(
            [
                *exec_,
                "pg_restore",
                "-U",
                user,
                "-d",
                scratch,
                "--no-owner",
                "--exit-on-error",
                inside,
            ]
        )
        _run([*exec_, "rm", "-f", inside])

    restored = dump.with_name(dump.stem + "_restored.json")
    try:
        if _verify(["snapshot", "--database-url", scratch_url, "--out", str(restored)]) != 0:
            return 1
        result = _verify(["compare", str(fingerprint), str(restored)])
    finally:
        if opts.local:
            _run(["psql", "-d", "postgres", "-c", drop], env=_libpq_env(url))
        else:
            _run(
                ["docker", "exec", opts.container, "psql", "-U", u.username or "postgres"]
                + ["-d", "postgres", "-c", drop]
            )
        restored.unlink(missing_ok=True)
    print("\nRestore check passed." if result == 0 else "\nRestore check FAILED (see above).")
    return result


def main() -> int:
    opts = _parse_args()
    if opts.local:
        missing = [tool for tool in ("pg_dump", "pg_restore", "psql") if not shutil.which(tool)]
        if missing:
            print(f"--local needs {', '.join(missing)} on PATH")
            return 1
    return backup(opts) if opts.command == "backup" else restore_check(opts)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(main())
