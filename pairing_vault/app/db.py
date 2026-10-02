"""SQLite storage for device entries."""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROTOCOLS = ("matter", "zwave", "insteon", "other")

# Fields a client may set. id, uuid and timestamps are managed here.
EDITABLE_FIELDS = (
    "name",
    "protocol",
    "qr_payload",
    "manual_code",
    "dsk",
    "insteon_id",
    "serial_number",
    "manufacturer",
    "model",
    "location",
    "notes",
)

# Each entry is a list of statements; the index + 1 is the schema version it
# brings the database to. Append new migrations, never edit old ones.
MIGRATIONS: list[list[str]] = [
    [
        """
        CREATE TABLE devices (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid          TEXT NOT NULL UNIQUE,
            name          TEXT NOT NULL,
            protocol      TEXT NOT NULL CHECK (protocol IN ('matter', 'zwave', 'other')),
            qr_payload    TEXT NOT NULL DEFAULT '',
            manual_code   TEXT NOT NULL DEFAULT '',
            dsk           TEXT NOT NULL DEFAULT '',
            serial_number TEXT NOT NULL DEFAULT '',
            manufacturer  TEXT NOT NULL DEFAULT '',
            model         TEXT NOT NULL DEFAULT '',
            location      TEXT NOT NULL DEFAULT '',
            notes         TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
        """,
        "CREATE INDEX devices_name ON devices (name COLLATE NOCASE)",
    ],
    # Add Insteon. SQLite can't change a CHECK constraint in place, so the
    # table is rebuilt without it; clean() validates protocol instead.
    [
        """
        CREATE TABLE devices_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid          TEXT NOT NULL UNIQUE,
            name          TEXT NOT NULL,
            protocol      TEXT NOT NULL,
            qr_payload    TEXT NOT NULL DEFAULT '',
            manual_code   TEXT NOT NULL DEFAULT '',
            dsk           TEXT NOT NULL DEFAULT '',
            insteon_id    TEXT NOT NULL DEFAULT '',
            serial_number TEXT NOT NULL DEFAULT '',
            manufacturer  TEXT NOT NULL DEFAULT '',
            model         TEXT NOT NULL DEFAULT '',
            location      TEXT NOT NULL DEFAULT '',
            notes         TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
        """,
        """
        INSERT INTO devices_new (id, uuid, name, protocol, qr_payload, manual_code, dsk,
                                 serial_number, manufacturer, model, location, notes,
                                 created_at, updated_at)
        SELECT id, uuid, name, protocol, qr_payload, manual_code, dsk,
               serial_number, manufacturer, model, location, notes, created_at, updated_at
        FROM devices
        """,
        "DROP TABLE devices",
        "ALTER TABLE devices_new RENAME TO devices",
        "CREATE INDEX devices_name ON devices (name COLLATE NOCASE)",
    ],
]


class ValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(data: dict, *, partial: bool = False) -> dict:
    """Validate and normalise client input. Unknown keys are ignored."""
    out: dict[str, str] = {}
    errors: dict[str, str] = {}
    for field in EDITABLE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if value is None:
            value = ""
        if not isinstance(value, str):
            errors[field] = "must be text"
            continue
        # Notes keep their line breaks; everything else is a single trimmed line.
        out[field] = value.strip() if field == "notes" else " ".join(value.split())

    # Insteon IDs are six hex digits, printed as 1A.2B.3C.
    insteon = re.fullmatch(r"([0-9a-f]{2})[.:\s-]?([0-9a-f]{2})[.:\s-]?([0-9a-f]{2})",
                           out.get("insteon_id", ""), re.I)
    if insteon:
        out["insteon_id"] = ".".join(insteon.groups()).upper()

    if not partial or "name" in out:
        if not out.get("name"):
            errors["name"] = "is required"
    if not partial or "protocol" in out:
        protocol = out.get("protocol", "").lower()
        if protocol not in PROTOCOLS:
            errors["protocol"] = f"must be one of {', '.join(PROTOCOLS)}"
        else:
            out["protocol"] = protocol
    if errors:
        raise ValidationError(errors)
    return out


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            # One transaction, so a failed migration leaves nothing half done.
            conn.execute("BEGIN")
            for target, statements in enumerate(MIGRATIONS[version:], start=version + 1):
                for sql in statements:
                    conn.execute(sql)
                conn.execute(f"PRAGMA user_version = {target}")

    def list(self, query: str = "") -> list[dict]:
        sql = "SELECT * FROM devices"
        params: list[str] = []
        if query:
            like = f"%{query}%"
            cols = ("name", "location", "serial_number", "manufacturer", "model",
                    "qr_payload", "manual_code", "dsk", "insteon_id", "notes")
            sql += " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols)
            params = [like] * len(cols)
        sql += " ORDER BY name COLLATE NOCASE, id"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def get(self, device_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return dict(row) if row else None

    def create(self, data: dict) -> dict:
        fields = clean(data)
        now = _now()
        fields.update(uuid=str(uuid.uuid4()), created_at=now, updated_at=now)
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self._connect() as conn:
            cur = conn.execute(
                f"INSERT INTO devices ({cols}) VALUES ({marks})", list(fields.values())
            )
            new_id = cur.lastrowid
        return self.get(new_id)

    def update(self, device_id: int, data: dict) -> dict | None:
        fields = clean(data, partial=True)
        if not fields:
            return self.get(device_id)
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{c} = ?" for c in fields)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE devices SET {assignments} WHERE id = ?",
                [*fields.values(), device_id],
            )
            if cur.rowcount == 0:
                return None
        return self.get(device_id)

    def delete(self, device_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        return cur.rowcount > 0
