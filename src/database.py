# src/database.py
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DB_PATH, logger


@contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасного подключения к БД."""
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    # Включаем поддержку внешних ключей
    conn.execute("PRAGMA foreign_keys = ON;")
    # Возвращаем строки как словари для удобства (по ключам)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Создает таблицы, если они еще не существуют."""
    logger.info("Инициализация базы данных...")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Таблица рыночных предметов (то, по чему ищем цену)
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

        # 2. Таблица твоих конкретных предметов в инвентаре
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

        # 3. Таблица истории цен (временные ряды)
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

        # Индексы для ускорения поиска по истории
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_item_time 
            ON price_history(market_item_id, recorded_at);
        """)

        conn.commit()
    logger.info("Таблицы успешно проверены/созданы.")


if __name__ == "__main__":
    init_db()
