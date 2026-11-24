"""Local SQLite storage for APP_MODE=demo.

It has the same method names as DynamoStore, so the rest of the app does not care which one
is in use. Data is kept in a file (instance/quickbite_demo.db), so it survives restarts.
This store is for local testing only. It is never used in aws mode.
"""
import json
import os
import sqlite3
from contextlib import contextmanager

from services.errors import DuplicateItemError, DuplicateOrderError, DuplicateStudentError
from services.menu_data import SAMPLE_MENU


class DemoStore:
    def __init__(self, db_path):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db_path = db_path
        with self._db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS menu_items (
                    item_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    order_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_id TEXT,
                    data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_orders_date ON orders (order_date, created_at);
                CREATE TABLE IF NOT EXISTS students (
                    phone TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL
                );
                """
            )
            order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
            if "user_id" not in order_columns:
                conn.execute("ALTER TABLE orders ADD COLUMN user_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_date ON orders (user_id, created_at)")
            legacy_statuses = {
                "Pending": "Placed",
                "Ready": "Ready for Pickup",
                "Collected": "Completed",
            }
            for row in conn.execute("SELECT order_id, status, data, user_id FROM orders").fetchall():
                new_status = legacy_statuses.get(row["status"])
                order = json.loads(row["data"])
                order["status"] = new_status or order.get("status", row["status"])
                order["user_id"] = order.get("user_id") or row["user_id"] or order.get("student_phone")
                order.setdefault("payment_method", "counter")
                order.setdefault("payment_status", "pay_at_pickup")
                if (
                    new_status or not row["user_id"]
                    or "payment_method" not in json.loads(row["data"])
                    or "payment_status" not in json.loads(row["data"])
                ):
                    conn.execute(
                        "UPDATE orders SET status = ?, user_id = ?, data = ? WHERE order_id = ?",
                        (order["status"], order["user_id"], json.dumps(order), row["order_id"]),
                    )

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def seed_if_empty(self):
        existing_ids = {item["item_id"] for item in self.list_menu()}
        missing = [item for item in SAMPLE_MENU if item["item_id"] not in existing_ids]
        if missing:
            self.upsert_menu_items(missing)

    def list_menu(self):
        with self._db() as conn:
            rows = conn.execute("SELECT data FROM menu_items ORDER BY item_id").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def upsert_menu_items(self, items):
        with self._db() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO menu_items (item_id, data) VALUES (?, ?)",
                [(item["item_id"], json.dumps(item)) for item in items],
            )

    def add_menu_item(self, item):
        try:
            with self._db() as conn:
                conn.execute(
                    "INSERT INTO menu_items (item_id, data) VALUES (?, ?)",
                    (item["item_id"], json.dumps(item)),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateItemError(item["item_id"]) from exc

    def update_menu_item(self, item_id, updates):
        with self._db() as conn:
            row = conn.execute("SELECT data FROM menu_items WHERE item_id = ?", (item_id,)).fetchone()
            if row is None:
                return None
            item = json.loads(row["data"])
            item.update(updates)
            conn.execute(
                "UPDATE menu_items SET data = ? WHERE item_id = ?",
                (json.dumps(item), item_id),
            )
        return item

    def get_student_by_phone(self, phone):
        with self._db() as conn:
            row = conn.execute(
                "SELECT phone, student_id, name FROM students WHERE phone = ?", (phone,)
            ).fetchone()
        return dict(row) if row else None

    def create_student(self, student):
        try:
            with self._db() as conn:
                conn.execute(
                    "INSERT INTO students (phone, student_id, name) VALUES (?, ?, ?)",
                    (student["phone"], student["student_id"], student["name"]),
                )
        except sqlite3.IntegrityError as exc:
            if self.get_student_by_phone(student["phone"]):
                raise DuplicateStudentError("phone", "An account with this phone number already exists.") from exc
            with self._db() as conn:
                duplicate_id = conn.execute(
                    "SELECT 1 FROM students WHERE student_id = ?", (student["student_id"],)
                ).fetchone()
            if duplicate_id:
                raise DuplicateStudentError(
                    "student_id", "An account with this College ID Card Number already exists."
                ) from exc
            raise

    def put_order(self, order):
        try:
            with self._db() as conn:
                conn.execute(
                    "INSERT INTO orders (order_id, order_date, created_at, status, user_id, data) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        order["order_id"], order["order_date"], order["created_at"],
                        order["status"], order["user_id"], json.dumps(order),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateOrderError(order["order_id"]) from exc

    def get_order(self, order_id):
        with self._db() as conn:
            row = conn.execute("SELECT data FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_orders_by_date(self, order_date):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT data FROM orders WHERE order_date = ? ORDER BY created_at", (order_date,)
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def list_orders_by_user(self, user_id):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT data FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def mark_order_paid(self, order_id, updated_at):
        with self._db() as conn:
            row = conn.execute("SELECT data FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if row is None:
                return False
            order = json.loads(row["data"])
            if order.get("payment_status") in ("paid", "paid_at_order"):
                return False
            order["payment_status"] = "paid"
            order["updated_at"] = updated_at
            conn.execute(
                "UPDATE orders SET data = ? WHERE order_id = ?",
                (json.dumps(order), order_id),
            )
        return True

    def update_status(self, order_id, expected_status, new_status, updated_at):
        """Change the status only if it still equals expected_status. Returns True on success."""
        with self._db() as conn:
            row = conn.execute("SELECT data FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if row is None:
                return False
            order = json.loads(row["data"])
            if order["status"] != expected_status:
                return False
            order["status"] = new_status
            order["updated_at"] = updated_at
            cursor = conn.execute(
                "UPDATE orders SET status = ?, data = ? WHERE order_id = ? AND status = ?",
                (new_status, json.dumps(order), order_id, expected_status),
            )
            return cursor.rowcount == 1
