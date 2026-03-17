# src/repositories/price_repository.py
from typing import List, Dict, Optional
from database import get_db_connection
from domain.models import PriceRecord, AlertEvent


class PriceRepository:
    """Управляет историей цен и историей сработавших алертов."""

    def add_price_record(self, record: PriceRecord):
        """Записывает новый срез цены."""
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO price_history (market_item_id, price_real, volume)
                VALUES (?, ?, ?)
            """, (record.market_item_id, record.price, record.volume))
            conn.commit()

    def get_price_windows(self) -> List[Dict]:
        """SQL Машина времени: Достает цены и объемы по окнам."""
        query = """
            SELECT 
                m.id AS market_item_id,
                m.market_hash_name,

                (SELECT price_real FROM price_history 
                 WHERE market_item_id = m.id ORDER BY recorded_at DESC LIMIT 1) AS current_price,

                -- ДОБАВЛЕНО: Достаем последний объем продаж
                (SELECT volume FROM price_history 
                 WHERE market_item_id = m.id ORDER BY recorded_at DESC LIMIT 1) AS current_volume,

                (SELECT price_real FROM price_history 
                 WHERE market_item_id = m.id AND recorded_at <= datetime('now', '-1 day') 
                 ORDER BY recorded_at DESC LIMIT 1) AS price_24h,

                (SELECT price_real FROM price_history 
                 WHERE market_item_id = m.id AND recorded_at <= datetime('now', '-7 days') 
                 ORDER BY recorded_at DESC LIMIT 1) AS price_7d,

                i.baseline_price

            FROM market_items m
            JOIN inventory_assets i ON m.id = i.market_item_id
            GROUP BY m.id
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def has_recent_alert(self, event: AlertEvent) -> bool:
        """Проверяет, был ли такой же алерт за последние 24 часа."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM alert_history 
                WHERE market_item_id = ? 
                  AND window = ? 
                  AND direction = ? 
                  AND triggered_at >= datetime('now', '-1 day')
            """, (event.market_item_id, event.window, event.direction))
            return bool(cursor.fetchone())

    def log_alert_event(self, event: AlertEvent):
        """Записывает факт отправки алерта (кулдаун)."""
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO alert_history (market_item_id, window, direction)
                VALUES (?, ?, ?)
            """, (event.market_item_id, event.window, event.direction))
            conn.commit()

    def get_items_with_latest_price(self) -> list[dict]:
        """Достает уникальные предметы инвентаря + их последнюю известную цену."""
        query = """
                SELECT 
                    m.id, 
                    m.market_hash_name,
                    (SELECT price_real FROM price_history 
                     WHERE market_item_id = m.id ORDER BY recorded_at DESC LIMIT 1) as latest_price
                FROM market_items m
                JOIN inventory_assets i ON m.id = i.market_item_id
                GROUP BY m.id
            """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]