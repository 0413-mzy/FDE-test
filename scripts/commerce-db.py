#!/usr/bin/env python3
"""Local developer inspection of an existing database. Never prints its connection URL."""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, text

SECRET_FIELDS = {
    "password",
    "current_password",
    "new_password",
    "password_hash",
    "token",
    "token_digest",
    "code",
    "request_hash",
    "email_digest",
    "ip_digest",
}
HISTORY_TABLE = "commerce_record_history"


class InspectionError(Exception):
    pass


def identifier(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
        raise argparse.ArgumentTypeError("Use a plain PostgreSQL table name.")
    return value


def bounded(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("Limit must be between 1 and 100.")
    return number


def offset_value(value):
    number = int(value)
    if not 0 <= number <= 1000000:
        raise argparse.ArgumentTypeError("Offset must be between 0 and 1000000.")
    return number


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    config = parser.add_mutually_exclusive_group()
    config.add_argument(
        "--local-demo", action="store_true", help="Read the existing local demo pointer."
    )
    config.add_argument(
        "--runtime-file", type=Path, help="Private runtime.json; URL stays internal."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--tables", action="store_true")
    action.add_argument("--describe", type=identifier, metavar="TABLE")
    action.add_argument("--rows", type=identifier, metavar="TABLE")
    action.add_argument("--history", type=identifier, metavar="ENTITY_TABLE")
    action.add_argument("--connection-info", action="store_true")
    action.add_argument(
        "--psql", action="store_true", help="Open local psql with read-only default."
    )
    parser.add_argument("--id", type=UUID, help="Filter a history entity UUID.")
    parser.add_argument("--limit", type=bounded, default=20)
    parser.add_argument("--offset", type=offset_value, default=0)
    parser.add_argument(
        "--export", type=Path, help="Create a new private CSV file; never overwrite."
    )
    args = parser.parse_args(argv)
    if args.id is not None and not args.history:
        parser.error("--id is only valid with --history.")
    if args.export and not (args.rows or args.history):
        parser.error("--export requires --rows or --history.")
    return args


def configuration(args):
    path = args.runtime_file
    if args.local_demo:
        folder = Path("/private/tmp/fde-commerce-step3-path.txt").read_text().strip()
        path = Path(folder) / "runtime.json"
    url = json.loads(path.read_text())["database_url"] if path else os.environ.get("DATABASE_URL")
    if not url:
        raise InspectionError("Supply --local-demo, --runtime-file or explicit DATABASE_URL.")
    return url


def redact(value):
    if isinstance(value, dict):
        return {
            key: redact(item) for key, item in value.items() if key.lower() not in SECRET_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def safe_rows(rows):
    return [redact(dict(row)) for row in rows]


def export_csv(path, rows):
    # Exclusive creation keeps previous exports intact and local records private.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
        fields = list(rows[0]) if rows else []
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, default=str)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def inspect_database(engine, args):
    quote = engine.dialect.identifier_preparer.quote_identifier
    with engine.begin() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        schema = conn.scalar(text("SELECT current_schema()"))
        if not schema:
            raise InspectionError("No visible database schema configured.")
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname=current_schema() ORDER BY tablename"
                )
            )
            .scalars()
            .all()
        )
        if args.connection_info or args.psql:
            return {
                "database": engine.url.database,
                "user": engine.url.username,
                "host": engine.url.query.get("host") or engine.url.host,
                "port": engine.url.query.get("port") or engine.url.port or 5432,
                "schema": schema,
                "server_version": conn.scalar(text("SHOW server_version")),
            }
        if args.tables:
            return {
                "schema": schema,
                "tables": [
                    {
                        "table": table,
                        "rows": conn.scalar(
                            text(f"SELECT count(*) FROM {quote(schema)}.{quote(table)}")
                        ),
                    }
                    for table in tables
                ],
            }
        target = args.describe or args.rows or args.history
        if target not in tables:
            raise InspectionError("Requested table does not exist in the configured schema.")
        if args.describe:
            columns = (
                conn.execute(
                    text(
                        "SELECT column_name,data_type,is_nullable,column_default "
                        "FROM information_schema.columns "
                        "WHERE table_schema=:schema AND table_name=:table "
                        "ORDER BY ordinal_position"
                    ),
                    {"schema": schema, "table": target},
                )
                .mappings()
                .all()
            )
            return {"schema": schema, "table": target, "columns": [dict(row) for row in columns]}
        params = {"limit": args.limit, "offset": args.offset}
        if args.history:
            if HISTORY_TABLE not in tables:
                raise InspectionError("History migration0006 has not been applied.")
            tracked = conn.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema AND c.relname=:table "
                    "AND t.tgname='commerce_history_record' AND NOT t.tgisinternal)"
                ),
                {"schema": schema, "table": target},
            )
            if not tracked:
                raise InspectionError("Requested table is not a tracked commerce business table.")
            condition = "entity_table=:table"
            params["table"] = target
            if args.id:
                condition += " AND entity_id=:entity"
                params["entity"] = args.id
            query = f"SELECT * FROM {quote(schema)}.{quote(HISTORY_TABLE)} WHERE {condition} "
            query += "ORDER BY id DESC LIMIT :limit OFFSET :offset"
        else:
            columns = (
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema=:schema AND table_name=:table AND data_type<>'bytea' "
                        "ORDER BY ordinal_position"
                    ),
                    {"schema": schema, "table": target},
                )
                .scalars()
                .all()
            )
            visible = [name for name in columns if name.lower() not in SECRET_FIELDS]
            quoted = ",".join('"' + name.replace('"', '""') + '"' for name in visible)
            query = f"SELECT {quoted} FROM {quote(schema)}.{quote(target)} "
            query += ("ORDER BY id " if "id" in columns else "") + "LIMIT :limit OFFSET :offset"
        rows = safe_rows(conn.execute(text(query), params).mappings().all())
        if args.export:
            export_csv(args.export, rows)
        return {
            "schema": schema,
            "table": target,
            "rows": rows,
            "limit": args.limit,
            "offset": args.offset,
            "credentials_omitted": True,
        }


def psql(engine, info):
    binary = shutil.which("psql")
    if not binary:
        fallback = Path("/opt/homebrew/opt/postgresql@17/bin/psql")
        binary = str(fallback) if fallback.is_file() else None
    if not binary:
        raise InspectionError("psql was not found; use the closed read-only CLI actions.")
    identifier(info["schema"])
    env = dict(
        os.environ,
        PGDATABASE=info["database"],
        PGUSER=info["user"],
        PGHOST=str(info["host"] or "localhost"),
        PGPORT=str(info["port"]),
        PGOPTIONS=f"-c search_path={info['schema']} -c default_transaction_read_only=on "
        "-c timezone=Asia/Kuala_Lumpur",
    )
    if engine.url.password:
        env["PGPASSWORD"] = engine.url.password
    print(
        "Opening developer psql with read-only default and Malaysia display time. "
        "Database-owner permissions are not changed.",
        flush=True,
    )
    return subprocess.call(
        [binary, "--no-psqlrc", "--set", "ON_ERROR_STOP=1", "--pset", "pager=off"], env=env
    )


def main(argv=None):
    args = arguments(argv)
    engine = None
    try:
        engine = create_engine(configuration(args), hide_parameters=True)
        result = inspect_database(engine, args)
        if args.psql:
            return psql(engine, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except InspectionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except FileExistsError:
        print("Export path already exists; choose a new file.", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Database inspection failed. Check private configuration and database availability.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
