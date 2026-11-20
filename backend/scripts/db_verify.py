"""Manual tool: prove a migration kept the data intact. Read-only, never changes anything.

`snapshot` records, for every table in the public schema, its row count and one fingerprint per
column: an md5 over the md5 of each row's value, sorted, so row order does not matter and NULLs
count. JSON and JSONB values are fingerprinted as parsed values (cast to jsonb), so converting a
column from JSON to JSONB leaves its fingerprint unchanged; anything that changes a value does
not. Timestamps are read in UTC so the server's time zone cannot change a fingerprint.

`compare` lists every difference between two snapshots and exits with 1 if any of them was not
expected. Intended changes are named with --allow (a table, `table.*`, or `table.column`).
A json <-> jsonb type change with an unchanged fingerprint is reported as expected.

Typical use around a migration (from backend/, venv active):
    python scripts/db_verify.py snapshot --out before.json
    alembic upgrade head
    python scripts/db_verify.py snapshot --out after.json
    python scripts/db_verify.py compare before.json after.json --allow users.firebase_uid

--database-url points it at another database (for example the rehearsal copy) instead of
DATABASE_URL.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

_JSON_TYPES = {"json", "jsonb"}
_SKIPPED_TABLES = {"alembic_version"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot", help="fingerprint every table and column")
    snap.add_argument("--out", required=True, type=Path, help="where to write the snapshot (JSON)")
    snap.add_argument("--database-url", help="defaults to DATABASE_URL")
    comp = sub.add_parser("compare", help="list differences between two snapshots")
    comp.add_argument("before", type=Path)
    comp.add_argument("after", type=Path)
    comp.add_argument(
        "--allow",
        action="append",
        default=[],
        help="an intended change: TABLE, TABLE.*, or TABLE.COLUMN (repeatable)",
    )
    return parser.parse_args()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _value_expr(column: str, udt_name: str) -> str:
    col = _quote(column)
    return f"{col}::jsonb::text" if udt_name in _JSON_TYPES else f"{col}::text"


async def _tables(conn: AsyncConnection) -> list[str]:
    result = await conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
    )
    return [name for (name,) in result if name not in _SKIPPED_TABLES]


async def _columns(conn: AsyncConnection, table: str) -> list[tuple[str, str]]:
    result = await conn.execute(
        text(
            "SELECT column_name, udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table ORDER BY ordinal_position"
        ),
        {"table": table},
    )
    return [(name, udt) for name, udt in result]


async def _fingerprint_table(conn: AsyncConnection, table: str) -> dict[str, Any]:
    columns = await _columns(conn, table)
    parts = ["count(*)"]
    for name, udt in columns:
        row_hash = f"coalesce(md5({_value_expr(name, udt)}), 'NULL')"
        # Byte order, not the database's collation: the same data must give the same fingerprint
        # on servers whose C libraries sort text differently (Alpine musl vs Debian glibc).
        ordered = f'{row_hash} COLLATE "C"'
        parts.append(f"md5(coalesce(string_agg({row_hash}, ',' ORDER BY {ordered}), ''))")
    row = (await conn.execute(text(f"SELECT {', '.join(parts)} FROM {_quote(table)}"))).one()
    return {
        "rows": row[0],
        "columns": {
            name: {"type": udt, "hash": row[i + 1]} for i, (name, udt) in enumerate(columns)
        },
    }


async def _snapshot(database_url: str, out: Path) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text("SET TIME ZONE 'UTC'"))
            version_rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
            versions = sorted(v for (v,) in version_rows)
            tables: dict[str, Any] = {}
            for table in await _tables(conn):
                tables[table] = await _fingerprint_table(conn, table)
                print(f"  {table:<40}{tables[table]['rows']:>10} rows")
            await conn.rollback()
    finally:
        await engine.dispose()
    url = make_url(database_url)
    snapshot = {
        "taken_at": datetime.now(UTC).isoformat(),
        "database": f"{url.host}:{url.port}/{url.database}",
        "alembic_version": versions,
        "tables": tables,
    }
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\n{len(tables)} tables, alembic {versions}. Written to {out}")
    return 0


def _allowed(allow: list[str], table: str, column: str | None = None) -> bool:
    keys = {table, f"{table}.*"} if column is None else {table, f"{table}.*", f"{table}.{column}"}
    return any(a in keys for a in allow)


def _compare(before_path: Path, after_path: Path, allow: list[str]) -> int:
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))
    expected: list[str] = []
    unexpected: list[str] = []

    def note(message: str, ok: bool) -> None:
        (expected if ok else unexpected).append(message)

    b_tables, a_tables = before["tables"], after["tables"]
    for table in sorted(set(b_tables) - set(a_tables)):
        note(f"table removed: {table}", _allowed(allow, table))
    for table in sorted(set(a_tables) - set(b_tables)):
        note(f"table added: {table} ({a_tables[table]['rows']} rows)", _allowed(allow, table))
    for table in sorted(set(b_tables) & set(a_tables)):
        b, a = b_tables[table], a_tables[table]
        if b["rows"] != a["rows"]:
            note(f"{table}: rows {b['rows']} -> {a['rows']}", _allowed(allow, table))
        b_cols, a_cols = b["columns"], a["columns"]
        for col in sorted(set(b_cols) - set(a_cols)):
            note(f"{table}.{col}: column removed", _allowed(allow, table, col))
        for col in sorted(set(a_cols) - set(b_cols)):
            note(f"{table}.{col}: column added", _allowed(allow, table, col))
        for col in sorted(set(b_cols) & set(a_cols)):
            bc, ac = b_cols[col], a_cols[col]
            same_hash = bc["hash"] == ac["hash"]
            if bc["type"] != ac["type"]:
                json_only = {bc["type"], ac["type"]} <= _JSON_TYPES and same_hash
                note(
                    f"{table}.{col}: type {bc['type']} -> {ac['type']}"
                    + (", values unchanged" if same_hash else ", VALUES CHANGED"),
                    json_only or _allowed(allow, table, col),
                )
            elif not same_hash:
                note(f"{table}.{col}: values changed", _allowed(allow, table, col))

    print(
        f"before: {before['database']} alembic {before['alembic_version']} ({before['taken_at']})"
    )
    print(f"after:  {after['database']} alembic {after['alembic_version']} ({after['taken_at']})")
    print(f"\nExpected differences ({len(expected)}):")
    for line in expected or ["  none"]:
        print(f"  {line}" if line != "  none" else line)
    print(f"\nUNEXPECTED differences ({len(unexpected)}):")
    for line in unexpected or ["  none"]:
        print(f"  {line}" if line != "  none" else line)
    if unexpected:
        print("\nFAIL: something changed that was not named with --allow. Stop and investigate.")
        return 1
    print("\nOK: every table and column matches, apart from the expected differences.")
    return 0


async def _main() -> int:
    args = _parse_args()
    if args.command == "snapshot":
        return await _snapshot(args.database_url or get_settings().database_url, args.out)
    return _compare(args.before, args.after, args.allow)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(_main()))
