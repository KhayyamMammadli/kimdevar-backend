"""SQLite pilot storage. All connections enable FK checks; data survives restarts."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "data/kimdevar.db")


@contextmanager
def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', district TEXT NOT NULL DEFAULT 'Xətai');
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS stores(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL, district TEXT NOT NULL, address TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', categories TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, hours TEXT NOT NULL DEFAULT '09:00–20:00');
        CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, filename TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, brand TEXT NOT NULL, model TEXT NOT NULL, part TEXT NOT NULL, budget REAL NOT NULL, district TEXT NOT NULL, urgency TEXT NOT NULL, quality TEXT NOT NULL, note TEXT NOT NULL, image_id TEXT REFERENCES uploads(id) ON DELETE SET NULL, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE, store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE, price REAL NOT NULL, quality TEXT NOT NULL, condition TEXT NOT NULL, stock TEXT NOT NULL, installation REAL NOT NULL, delivery INTEGER NOT NULL, warranty INTEGER NOT NULL, note TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', UNIQUE(request_id,store_id));
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE, buyer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE, UNIQUE(request_id,store_id));
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, sender_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, text TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, body TEXT NOT NULL, target_id TEXT, kind TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS favorites(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE, PRIMARY KEY(user_id,store_id));
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE SET NULL, reason TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_requests_buyer ON requests(buyer_id);
        CREATE INDEX IF NOT EXISTS ix_offers_request ON offers(request_id);
        CREATE INDEX IF NOT EXISTS ix_messages_conversation ON messages(conversation_id,created_at);
        """)
