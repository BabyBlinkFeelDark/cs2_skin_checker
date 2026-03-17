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
    # Возвращаем строки как словари для удобства
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Создает таблицы, если они еще не существуют, и проводит миграции."""
    logger.info("Инициализация базы данных...")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Таблица рыночных предметов
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

        # 2. Таблица предметов в инвентаре
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_assets (
                asset_id TEXT PRIMARY KEY,
                market_item_id INTEGER NOT NULL,
                context_id TEXT NOT NULL,
                amount INTEGER DEFAULT 1,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                baseline_price REAL DEFAULT NULL,
                FOREIGN KEY (market_item_id) REFERENCES market_items (id) ON DELETE CASCADE
            )
        """)

        # 3. Таблица истории цен
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

        # 4. Таблица для бизнес-алертов
        cursor.execute("""
           CREATE TABLE IF NOT EXISTS alert_queue_biz (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               message_text TEXT NOT NULL,
               status TEXT DEFAULT 'pending',
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
        """)

        # 5. Таблица для инфо-алертов
        cursor.execute("""
           CREATE TABLE IF NOT EXISTS alert_queue_info (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               message_text TEXT NOT NULL,
               status TEXT DEFAULT 'pending',
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
        """)

        # 6. История алертов (Анти-спам)
        cursor.execute("""
           CREATE TABLE IF NOT EXISTS alert_history (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               market_item_id INTEGER NOT NULL,
               window TEXT NOT NULL,
               direction TEXT NOT NULL,
               triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY (market_item_id) REFERENCES market_items (id) ON DELETE CASCADE
           )
        """)

        # 7. НОВАЯ ТАБЛИЦА: Глобальные настройки приложения (Key-Value)
        cursor.execute("""
           CREATE TABLE IF NOT EXISTS app_settings (
               setting_key TEXT PRIMARY KEY,
               setting_value TEXT NOT NULL,
               updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
        """)

        # --- БЛОК МИГРАЦИЙ ---

        # Миграция: Проверяем baseline_price
        cursor.execute("PRAGMA table_info(inventory_assets)")
        columns = [info['name'] for info in cursor.fetchall()]
        if 'baseline_price' not in columns:
            logger.info("Миграция: Добавляем поле 'baseline_price' в таблицу 'inventory_assets'...")
            cursor.execute("ALTER TABLE inventory_assets ADD COLUMN baseline_price REAL DEFAULT NULL")

        # Миграция: Заполняем app_settings дефолтными значениями, если таблица пустая
        cursor.execute("SELECT COUNT(*) FROM app_settings")
        if cursor.fetchone()[0] == 0:
            logger.info("Инициализация базовых настроек в БД...")
            default_settings = [
                ('steam_id_64', ''),
                ('drop_threshold_percent', '30.0'),
                ('rise_threshold_percent', '25.0'),
                ('check_interval_hours', '1'),
                ('min_difference_dollars', '0.5'),
                ('telegram_biz_token', ''),
                ('telegram_biz_chat_id', ''),
                ('telegram_info_token', ''),
                ('telegram_info_chat_id', '')
            ]
            cursor.executemany("""
                INSERT INTO app_settings (setting_key, setting_value) 
                VALUES (?, ?)
            """, default_settings)

        # --- ИНДЕКСЫ ---
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_item_time 
            ON price_history(market_item_id, recorded_at);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_history_search 
            ON alert_history(market_item_id, window, direction, triggered_at);
        """)

        conn.commit()
    logger.info("Таблицы успешно проверены/созданы/обновлены.")


if __name__ == "__main__":
    init_db()
