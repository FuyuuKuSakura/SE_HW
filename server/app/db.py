"""数据库连接与初始化。

设计说明：
- 不用 ORM，直接用标准库 sqlite3。理由是这门课要讲清楚 SQL 本身，
  而且 sqlite3 的行锁 + rowcount 正好用来实现"条件更新防超卖"。
- 每个请求开一条连接，请求结束关闭。SQLite 打开连接极便宜，
  比维护连接池更简单，也不会踩到"多线程共用连接"的坑。
"""
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("ZZ_DB", os.path.join(BASE_DIR, "zzj.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    # SQLite 默认不启用外键，必须每条连接手动打开
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """只负责开/关连接。事务要自己再套一层 `with conn:`。"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


def is_empty() -> bool:
    if not os.path.exists(DB_PATH):
        return True
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='items'"
        ).fetchone()
        if not row or row[0] == 0:
            return True
        return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    finally:
        conn.close()
