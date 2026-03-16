import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DB_PATH, logger

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    logger.info("Инициализация базы данных...")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                market_hash_name TEXT NOT NULL,
                is_marketable BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(app_id, market_hash_name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_assets (
                asset_id TEXT PRIMARY KEY,
                market_item_id INTEGER NOT NULL,
                context_id TEXT NOT NULL,
                amount INTEGER DEFAULT 1,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (market_item_id) REFERENCES market_items (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_item_id INTEGER NOT NULL,
                price_real REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                volume INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (market_item_id) REFERENCES market_items (id) ON DELETE CASCADE
            )
        """)

        # Таблица для бизнес-алертов (рост/падение цен)
        cursor.execute("""
           CREATE TABLE IF NOT EXISTS alert_queue_biz (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               message_text TEXT NOT NULL,
               status TEXT DEFAULT 'pending',
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
        """)

        # Таблица для инфо-алертов (старт, краш, логи)
        cursor.execute("""
           CREATE TABLE IF NOT EXISTS alert_queue_info (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               message_text TEXT NOT NULL,
               status TEXT DEFAULT 'pending',
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_item_time 
            ON price_history(market_item_id, recorded_at);
        """)

        conn.commit()
    logger.info("Таблицы успешно проверены/созданы.")

if __name__ == "__main__":
    init_db()
