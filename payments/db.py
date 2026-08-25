"""The licence server's store: SQLite, three tables, no ORM.

``licences``   one row per purchase — key, tier, model, who owns it, whether it
               is still good, and the Stripe ids it came from.
``activations``one row per machine bound to a licence. Seat enforcement is a
               COUNT over this table.
``events``     an append-only log of everything that changed a licence, so a
               billing dispute can be answered from the database rather than
               from memory.

SQLite is the right size for this. A desktop app's licence traffic is a
handful of requests per customer per week; the whole store fits in a file that
can be backed up with ``cp``. The schema is small enough to move to Postgres
later, and the calls go through this module so that move is one file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS licences (
    key             TEXT PRIMARY KEY,
    tier            TEXT NOT NULL,
    model           TEXT NOT NULL,
    sku             TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',   -- active|cancelled|refunded
    max_machines    INTEGER NOT NULL DEFAULT 1,
    expires_at      REAL,             -- NULL for perpetual
    updates_until   REAL,             -- perpetual: end of the update window
    created_at      REAL NOT NULL,
    stripe_customer TEXT NOT NULL DEFAULT '',
    stripe_sub      TEXT NOT NULL DEFAULT '',
    extra_features  TEXT NOT NULL DEFAULT '[]',
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS activations (
    licence_key  TEXT NOT NULL,
    machine_id   TEXT NOT NULL,
    label        TEXT NOT NULL DEFAULT '',
    seat         INTEGER NOT NULL DEFAULT 1,
    first_seen   REAL NOT NULL,
    last_seen    REAL NOT NULL,
    released_at  REAL,
    PRIMARY KEY (licence_key, machine_id)
);

CREATE TABLE IF NOT EXISTS trials (
    machine_id  TEXT PRIMARY KEY,
    started_at  REAL NOT NULL,
    email       TEXT NOT NULL DEFAULT '',
    label       TEXT NOT NULL DEFAULT '',
    last_seen   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          REAL NOT NULL,
    licence_key TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_licences_email ON licences(email);
CREATE INDEX IF NOT EXISTS idx_licences_sub ON licences(stripe_sub);
CREATE INDEX IF NOT EXISTS idx_events_key ON events(licence_key);
"""


class Database:
    def __init__(self, path: str = "licenses.db") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because the WSGI server serves requests from
        # a thread pool; every write goes through a short transaction below.
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(SCHEMA)
        self._connection.commit()
        # See write(): one writer at a time across the server's threads.
        # Re-entrant so that a future caller nesting two write() blocks on one
        # thread deadlocks nobody; today nothing nests.
        self._write_lock = threading.RLock()

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """One write transaction, exclusive across threads.

        The lock is not belt-and-braces, it is load-bearing. Python's sqlite3
        serialises individual *statements*, but a transaction is begun
        implicitly by the first statement and ``with connection`` only decides
        whether to commit or roll back at the end. Two threads sharing this
        connection therefore land inside one transaction, and the first to
        leave commits both — or, if either raises, the rollback discards the
        other request's work as well.

        That is not theoretical. Without this lock, a webhook that had just
        created a paid licence loses the row when an unrelated activation
        fails a fraction of a second later: money taken, no licence issued.
        """
        with self._write_lock:
            with self._connection:  # commits on success, rolls back on error
                yield self._connection

    def query(self, sql: str, *args) -> List[sqlite3.Row]:
        return list(self._connection.execute(sql, args))

    def one(self, sql: str, *args) -> Optional[sqlite3.Row]:
        rows = self.query(sql, *args)
        return rows[0] if rows else None

    # -- licences ---------------------------------------------------------
    def create_licence(self, *, key: str, tier: str, model: str, sku: str = "",
                       email: str = "", name: str = "", max_machines: int = 1,
                       expires_at: Optional[float] = None,
                       updates_until: Optional[float] = None,
                       stripe_customer: str = "", stripe_sub: str = "",
                       extra_features: Optional[List[str]] = None,
                       notes: str = "") -> Dict[str, Any]:
        now = time.time()
        with self.write() as connection:
            connection.execute(
                "INSERT INTO licences (key, tier, model, sku, email, name, status,"
                " max_machines, expires_at, updates_until, created_at,"
                " stripe_customer, stripe_sub, extra_features, notes)"
                " VALUES (?,?,?,?,?,?,'active',?,?,?,?,?,?,?,?)",
                (key, tier, model, sku, email, name, max_machines, expires_at,
                 updates_until, now, stripe_customer, stripe_sub,
                 json.dumps(list(extra_features or [])), notes),
            )
        self.log(key, "created", f"{sku or tier} for {email or 'unknown'}")
        return self.licence(key) or {}

    def licence(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.one("SELECT * FROM licences WHERE key = ?", key)
        return _as_licence(row) if row else None

    def licence_by_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        row = self.one("SELECT * FROM licences WHERE stripe_sub = ?", subscription_id)
        return _as_licence(row) if row else None

    def licences_for_email(self, email: str) -> List[Dict[str, Any]]:
        rows = self.query("SELECT * FROM licences WHERE email = ? ORDER BY created_at",
                          email)
        return [_as_licence(row) for row in rows]

    def update_licence(self, key: str, **fields) -> Optional[Dict[str, Any]]:
        allowed = {"tier", "model", "sku", "email", "name", "status", "max_machines",
                   "expires_at", "updates_until", "stripe_customer", "stripe_sub",
                   "notes"}
        changes = {name: value for name, value in fields.items() if name in allowed}
        if "extra_features" in fields:
            changes["extra_features"] = json.dumps(list(fields["extra_features"] or []))
        if not changes:
            return self.licence(key)
        assignments = ", ".join(f"{name} = ?" for name in changes)
        with self.write() as connection:
            connection.execute(f"UPDATE licences SET {assignments} WHERE key = ?",
                               (*changes.values(), key))
        return self.licence(key)

    # -- activations ------------------------------------------------------
    def activations(self, key: str, include_released: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM activations WHERE licence_key = ?"
        if not include_released:
            sql += " AND released_at IS NULL"
        return [dict(row) for row in self.query(sql + " ORDER BY seat", key)]

    def activation(self, key: str, machine_id: str) -> Optional[Dict[str, Any]]:
        row = self.one("SELECT * FROM activations WHERE licence_key = ? AND machine_id = ?",
                       key, machine_id)
        return dict(row) if row else None

    def activate(self, key: str, machine_id: str, label: str = "",
                 max_machines: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Bind a machine, or touch an existing binding.

        Returns None when ``max_machines`` is given and the licence is full.

        Deciding and writing happen together under the write lock, and that is
        the whole point of this method. Both the seat number and the seat limit
        are derived from counting what is already there, so two activations
        arriving at the same moment would otherwise both read the old total:
        two machines handed the same seat number, and — worse — a three-seat
        licence quietly admitting a fourth machine.
        """
        now = time.time()
        seat = 0
        with self._write_lock:
            existing = self.activation(key, machine_id)
            if existing:
                with self._connection:
                    self._connection.execute(
                        "UPDATE activations SET last_seen = ?, released_at = NULL,"
                        " label = ? WHERE licence_key = ? AND machine_id = ?",
                        (now, label or existing["label"], key, machine_id))
                return self.activation(key, machine_id) or {}
            live = self.activations(key)
            if max_machines is not None and len(live) >= int(max_machines):
                return None
            taken = {row["seat"] for row in live}
            seat = next(number for number in range(1, 1000) if number not in taken)
            with self._connection:
                self._connection.execute(
                    "INSERT INTO activations (licence_key, machine_id, label, seat,"
                    " first_seen, last_seen) VALUES (?,?,?,?,?,?)",
                    (key, machine_id, label, seat, now, now))
        self.log(key, "activated", f"seat {seat}: {label or machine_id[:8]}")
        return self.activation(key, machine_id) or {}

    def release(self, key: str, machine_id: str) -> bool:
        """Free a seat. Returns whether there was one to free."""
        if not self.activation(key, machine_id):
            return False
        with self.write() as connection:
            connection.execute(
                "UPDATE activations SET released_at = ? WHERE licence_key = ?"
                " AND machine_id = ?", (time.time(), key, machine_id))
        self.log(key, "deactivated", machine_id[:8])
        return True

    def touch(self, key: str, machine_id: str) -> None:
        with self.write() as connection:
            connection.execute(
                "UPDATE activations SET last_seen = ? WHERE licence_key = ?"
                " AND machine_id = ?", (time.time(), key, machine_id))

    def seats_used(self, key: str) -> int:
        return len(self.activations(key))

    # -- trials -----------------------------------------------------------
    def trial(self, machine_id: str) -> Optional[Dict[str, Any]]:
        row = self.one("SELECT * FROM trials WHERE machine_id = ?", machine_id)
        return dict(row) if row else None

    def start_trial(self, machine_id: str, email: str = "",
                    label: str = "") -> Dict[str, Any]:
        """Record a trial, or return the existing one untouched.

        Returning the *original* ``started_at`` is the whole anti-reset
        mechanism: a machine that reinstalls gets its old clock back.
        """
        now = time.time()
        existing = self.trial(machine_id)
        if existing:
            with self.write() as connection:
                connection.execute("UPDATE trials SET last_seen = ? WHERE machine_id = ?",
                                   (now, machine_id))
            return existing
        with self.write() as connection:
            connection.execute(
                "INSERT INTO trials (machine_id, started_at, email, label, last_seen)"
                " VALUES (?,?,?,?,?)", (machine_id, now, email, label, now))
        self.log("", "trial_started", f"{label or machine_id[:8]} {email}".strip())
        return self.trial(machine_id) or {}

    # -- events -----------------------------------------------------------
    def log(self, key: str, kind: str, detail: str = "") -> None:
        with self.write() as connection:
            connection.execute(
                "INSERT INTO events (at, licence_key, kind, detail) VALUES (?,?,?,?)",
                (time.time(), key, kind, detail))

    def events(self, key: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        if key:
            rows = self.query("SELECT * FROM events WHERE licence_key = ?"
                              " ORDER BY id DESC LIMIT ?", key, limit)
        else:
            rows = self.query("SELECT * FROM events ORDER BY id DESC LIMIT ?", limit)
        return [dict(row) for row in rows]


def _as_licence(row: sqlite3.Row) -> Dict[str, Any]:
    licence = dict(row)
    try:
        licence["extra_features"] = json.loads(licence.get("extra_features") or "[]")
    except ValueError:
        licence["extra_features"] = []
    return licence
