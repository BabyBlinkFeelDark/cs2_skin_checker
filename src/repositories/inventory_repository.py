# src/repositories/inventory_repository.py
from typing import List, Set, Dict
from config import logger
from database import get_db_connection
from domain.models import InventoryAsset

class InventoryRepository:
    """Управляет сохранением и извлечением инвентаря пользователя."""

    def get_all_asset_ids(self) -> Set[str]:
        """Возвращает множество всех asset_id, которые сейчас лежат в базе."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT asset_id FROM inventory_assets")
            return set(row['asset_id'] for row in cursor.fetchall())

    def delete_assets(self, asset_ids: Set[str]):
        """Удаляет проданные предметы из базы."""
        if not asset_ids:
            return
        with get_db_connection() as conn:
            placeholders = ','.join('?' * len(asset_ids))
            conn.execute(f"DELETE FROM inventory_assets WHERE asset_id IN ({placeholders})", tuple(asset_ids))
            conn.commit()

    def sync_items(self, items: List[InventoryAsset], app_id: int):
        """Добавляет новые типы предметов и обновляет конкретные ассеты в инвентаре."""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            for item in items:
                # 1. Гарантируем, что MarketItem существует
                cursor.execute("""
                    INSERT OR IGNORE INTO market_items (app_id, market_hash_name)
                    VALUES (?, ?)
                """, (app_id, item.market_hash_name))

                # Узнаем его ID в базе
                cursor.execute("""
                    SELECT id FROM market_items 
                    WHERE app_id = ? AND market_hash_name = ?
                """, (app_id, item.market_hash_name))
                market_item_id = cursor.fetchone()['id']

                # 2. Вставляем/обновляем сам инвентарный предмет (Soft Sync)
                cursor.execute("""
                    INSERT INTO inventory_assets (asset_id, market_item_id, context_id, amount, last_seen_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(asset_id) DO UPDATE SET
                        amount = excluded.amount,
                        last_seen_at = CURRENT_TIMESTAMP
                """, (item.asset_id, market_item_id, item.context_id, item.amount))

            conn.commit()

    def get_unique_market_items(self) -> List[Dict]:
        """Возвращает список уникальных предметов для парсинга цен.
        Отдает список словарей с 'id' и 'market_hash_name'."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT m.id, m.market_hash_name 
                FROM market_items m
                JOIN inventory_assets i ON m.id = i.market_item_id
            """)
            return [dict(row) for row in cursor.fetchall()]

    def set_baseline_price(self, market_item_id: int, price: float):
        """Фиксирует точку входа для новых предметов, если она еще не задана."""
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE inventory_assets
                SET baseline_price = ?
                WHERE market_item_id = ? AND baseline_price IS NULL
            """, (price, market_item_id))
            conn.commit()
