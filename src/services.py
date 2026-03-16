# src/services.py
import time
import random
from config import logger
from database import get_db_connection
from steam_api import SteamClient
from alerts_sender import send_toast

class WatcherService:
    def __init__(self, steam_id, drop_threshold=30.0, rise_threshold=25.0,min_diff_dollars: float = 0.5, proxy_url=None):
        self.steam_client = SteamClient(steam_id, proxy_url=proxy_url)
        self.drop_threshold = drop_threshold
        self.rise_threshold = rise_threshold
        self.min_diff_dollars = min_diff_dollars

    def sync_inventory(self):
        """Синхронизирует инвентарь пользователя с локальной базой."""
        logger.info("Запуск синхронизации инвентаря...")
        items = self.steam_client.fetch_inventory()

        if items is None:
            logger.error("Не удалось получить инвентарь. Синхронизация прервана.")
            return

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 1. Сначала добавляем новые market_items, если их еще нет в базе
            for item in items:
                cursor.execute("""
                    INSERT OR IGNORE INTO market_items (app_id, market_hash_name)
                    VALUES (?, ?)
                """, (self.steam_client.app_id, item['market_hash_name']))

            # 2. Очищаем старый слепок инвентаря (чтобы удалить то, что ты уже продал)
            # В реальном приложении можно делать 'soft delete', но для начала хватит полного обновления
            cursor.execute("DELETE FROM inventory_assets")

            # 3. Заполняем инвентарь актуальными данными
            for item in items:
                # Находим ID рыночного предмета
                cursor.execute("""
                    SELECT id FROM market_items 
                    WHERE app_id = ? AND market_hash_name = ?
                """, (self.steam_client.app_id, item['market_hash_name']))
                market_item_id = cursor.fetchone()['id']

                cursor.execute("""
                    INSERT INTO inventory_assets (asset_id, market_item_id, context_id, amount)
                    VALUES (?, ?, ?, ?)
                """, (item['asset_id'], market_item_id, self.steam_client.context_id, item['amount']))

            conn.commit()
        logger.info(f"Инвентарь успешно синхронизирован. Сохранено {len(items)} предметов.")

    def refresh_prices(self):
        """Обновляет цены для всех уникальных предметов в инвентаре."""
        logger.info("Запуск обновления цен...")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Достаем только те market_items, которые СЕЙЧАС есть у тебя в инвентаре
            cursor.execute("""
                SELECT DISTINCT m.id, m.market_hash_name 
                FROM market_items m
                JOIN inventory_assets i ON m.id = i.market_item_id
            """)
            items_to_check = cursor.fetchall()

        if not items_to_check:
            logger.info("Нет предметов для обновления цен.")
            return

        success_count = 0
        for row in items_to_check:
            market_item_id = row['id']
            market_hash_name = row['market_hash_name']

            price_data = self.steam_client.fetch_price(market_hash_name)

            if price_data:
                with get_db_connection() as conn:
                    conn.execute("""
                        INSERT INTO price_history (market_item_id, price_real, volume)
                        VALUES (?, ?, ?)
                    """, (market_item_id, price_data['price'], price_data['volume']))
                    conn.commit()
                success_count += 1
                logger.info(f"Обновлена цена: {market_hash_name} -> ${price_data['price']}")

            # КРИТИЧЕСКИ ВАЖНО: случайная задержка между запросами [web:140]
            # Steam быстро банит за частые запросы к market/priceoverview
            sleep_time = random.uniform(3.0, 6.0)
            logger.debug(f"Спим {sleep_time:.2f} сек. во избежание бана...")
            time.sleep(sleep_time)

        logger.info(f"Обновление цен завершено. Успешно: {success_count}/{len(items_to_check)}.")

    def check_price_alerts(self):
        """
        Сравнивает последнюю записанную цену со вчерашней (или предыдущей)
        и отправляет уведомление, если есть резкий скачок,
        превышающий как процентный порог, так и порог в долларах.
        """
        logger.info("Проверка сигналов изменения цены...")

        query = """
            WITH RankedPrices AS (
                SELECT 
                    p.market_item_id,
                    m.market_hash_name,
                    p.price_real,
                    p.recorded_at,
                    ROW_NUMBER() OVER(PARTITION BY p.market_item_id ORDER BY p.recorded_at DESC) as rn
                FROM price_history p
                JOIN market_items m ON p.market_item_id = m.id
            )
            SELECT 
                current.market_hash_name,
                current.price_real AS current_price,
                previous.price_real AS old_price
            FROM RankedPrices current
            JOIN RankedPrices previous 
                ON current.market_item_id = previous.market_item_id 
                AND previous.rn = 2
            WHERE current.rn = 1
        """

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            items = cursor.fetchall()

        alerts_found = 0

        for item in items:
            name = item['market_hash_name']
            current_price = item['current_price']
            old_price = item['old_price']

            if old_price <= 0:
                continue

            # 1. Считаем абсолютную разницу в долларах
            price_diff_abs = abs(current_price - old_price)

            # 2. Если изменение меньше нашего минимального порога (например, < $0.50), просто пропускаем этот скин
            if price_diff_abs < self.min_diff_dollars:
                continue

            # 3. Если абсолютный порог пройден, проверяем проценты
            percent_change = ((current_price - old_price) / old_price) * 100

            if percent_change <= -self.drop_threshold:
                msg = f"📉 ПАДЕНИЕ на {abs(percent_change):.1f}%! Было ${old_price:.2f}, стало ${current_price:.2f}"
                logger.warning(f"СИГНАЛ: {name} | {msg}")
                send_toast(f"Просадка: {name}", msg)
                alerts_found += 1

            elif percent_change >= self.rise_threshold:
                msg = f"📈 РОСТ на {percent_change:.1f}%! Было ${old_price:.2f}, стало ${current_price:.2f}"
                logger.warning(f"СИГНАЛ: {name} | {msg}")
                send_toast(f"Взлет: {name}", msg)
                alerts_found += 1

        logger.info(f"Проверка завершена. Найдено сигналов: {alerts_found}")