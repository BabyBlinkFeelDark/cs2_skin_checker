import time
import random
from config import logger
from database import get_db_connection
from steam_api import SteamClient
from alerts_sender import send_biz_alert

class WatcherService:
    def __init__(self, steam_id, drop_threshold=30.0, rise_threshold=25.0,min_diff_dollars: float = 0.5, proxy_url=None):
        self.steam_client = SteamClient(steam_id, proxy_url=proxy_url)
        self.drop_threshold = drop_threshold
        self.rise_threshold = rise_threshold
        self.min_diff_dollars = min_diff_dollars

    def sync_inventory(self):
        """Синхронизирует инвентарь пользователя с локальной базой (Soft Sync)."""
        logger.info("Запуск синхронизации инвентаря...")
        items = self.steam_client.fetch_inventory()

        if items is None:
            logger.error("Не удалось получить инвентарь. Синхронизация прервана.")
            return

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 1. Добавляем новые market_items (типы предметов), если их еще нет
            for item in items:
                cursor.execute("""
                    INSERT OR IGNORE INTO market_items (app_id, market_hash_name)
                    VALUES (?, ?)
                """, (self.steam_client.app_id, item['market_hash_name']))

            # 2. Получаем список asset_id, которые СЕЙЧАС лежат у нас в базе
            cursor.execute("SELECT asset_id FROM inventory_assets")
            db_assets = set(row['asset_id'] for row in cursor.fetchall())

            # 3. Получаем список asset_id, которые пришли из Steam
            steam_assets = set(item['asset_id'] for item in items)

            # 4. Находим разницу: что есть в базе, но пропало из Steam (предметы проданы/переданы)
            sold_assets = db_assets - steam_assets
            if sold_assets:
                placeholders = ','.join('?' * len(sold_assets))
                cursor.execute(f"DELETE FROM inventory_assets WHERE asset_id IN ({placeholders})", tuple(sold_assets))
                logger.info(f"Удалено {len(sold_assets)} проданных предметов из базы.")

            # 5. Добавляем новые или обновляем существующие (не трогая baseline_price)
            for item in items:
                cursor.execute("""
                    SELECT id FROM market_items 
                    WHERE app_id = ? AND market_hash_name = ?
                """, (self.steam_client.app_id, item['market_hash_name']))
                market_item_id = cursor.fetchone()['id']

                # Используем UPSERT: если asset_id новый - вставляем. Если уже есть - просто обновляем время.
                cursor.execute("""
                    INSERT INTO inventory_assets (asset_id, market_item_id, context_id, amount, last_seen_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(asset_id) DO UPDATE SET
                        amount = excluded.amount,
                        last_seen_at = CURRENT_TIMESTAMP
                """, (item['asset_id'], market_item_id, self.steam_client.context_id, item['amount']))

            conn.commit()
        logger.info(f"Инвентарь успешно синхронизирован. Актуально предметов: {len(items)}.")

    def refresh_prices(self):
        """Обновляет цены и фиксирует точку входа (baseline_price) для новых предметов."""
        logger.info("Запуск обновления цен...")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Достаем market_items, которые есть в инвентаре
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
                current_price = price_data['price']
                with get_db_connection() as conn:
                    # 1. Пишем новую цену в историю
                    conn.execute("""
                        INSERT INTO price_history (market_item_id, price_real, volume)
                        VALUES (?, ?, ?)
                    """, (market_item_id, current_price, price_data['volume']))

                    # 2. ФИКСИРУЕМ ТОЧКУ ВХОДА (Если предмет новый и baseline_price еще NULL)
                    conn.execute("""
                        UPDATE inventory_assets
                        SET baseline_price = ?
                        WHERE market_item_id = ? AND baseline_price IS NULL
                    """, (current_price, market_item_id))

                    conn.commit()

                success_count += 1
                logger.info(f"Обновлена цена: {market_hash_name} -> ${current_price}")

            # Рандомная задержка
            sleep_time = random.uniform(3.0, 6.0)
            logger.debug(f"Спим {sleep_time:.2f} сек. во избежание бана...")
            time.sleep(sleep_time)

        logger.info(f"Обновление цен завершено. Успешно: {success_count}/{len(items_to_check)}.")

    def check_price_alerts(self):
        """Проверяет цены и собирает красивую карточку со всей статистикой."""
        logger.info("Проверка сигналов изменения цены (Временные окна)...")

        query = """
            SELECT 
                m.id AS market_item_id,
                m.market_hash_name,

                (SELECT price_real FROM price_history 
                 WHERE market_item_id = m.id ORDER BY recorded_at DESC LIMIT 1) AS current_price,

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
            items = cursor.fetchall()

        alerts_found = 0

        for item in items:
            item_id = item['market_item_id']
            name = item['market_hash_name']
            current_price = item['current_price']

            if not current_price:
                continue

            windows = {
                '24ч': item['price_24h'],
                '7дн': item['price_7d'],
                'Точка входа': item['baseline_price']
            }

            # Ищем, какое окно стало триггером (пробило порог)
            trigger_window = None
            trigger_direction = None
            trigger_change = 0.0

            # Перебираем окна, чтобы найти первое пробитое (приоритет от коротких к длинным)
            for window_name, old_price in windows.items():
                if not old_price or old_price <= 0:
                    continue

                price_diff_abs = abs(current_price - old_price)
                if price_diff_abs < self.min_diff_dollars:
                    continue

                percent_change = ((current_price - old_price) / old_price) * 100

                direction = None
                if percent_change <= -self.drop_threshold:
                    direction = 'drop'
                elif percent_change >= self.rise_threshold:
                    direction = 'rise'

                if direction:
                    trigger_window = window_name
                    trigger_direction = direction
                    trigger_change = percent_change
                    break  # Как только нашли пробой - останавливаемся, это и есть наш триггер

            # Если ни одно окно не пробило порог - идем к следующему предмету
            if not trigger_direction:
                continue

            # --- АНТИ-СПАМ ФИЛЬТР ---
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM alert_history 
                    WHERE market_item_id = ? 
                      AND window = ? 
                      AND direction = ? 
                      AND triggered_at >= datetime('now', '-1 day')
                """, (item_id, trigger_window, trigger_direction))

                if cursor.fetchone():
                    continue

                conn.execute("""
                    INSERT INTO alert_history (market_item_id, window, direction)
                    VALUES (?, ?, ?)
                """, (item_id, trigger_window, trigger_direction))
                conn.commit()

            # --- ФОРМИРУЕМ КРАСИВОЕ СООБЩЕНИЕ ---
            # Вычисляем чистую цену (минус 15% комиссии Steam = делим на 1.15)
            net_price = current_price / 1.15

            title_emoji = "📈 ВЗЛЕТ" if trigger_direction == 'rise' else "📉 ПАДЕНИЕ"
            title = f"{title_emoji}: {name}"

            # Заголовок сообщения
            msg_lines = [
                f"⚡ Триггер: {trigger_window} ({trigger_change:+.1f}%)",
                f"💰 Текущая цена: ${current_price:.2f}",
                "➖➖➖➖➖➖",
                "📊 Динамика:"
            ]

            # Выводим статистику по всем окнам (даже если они не пробили порог)
            for w_name, old_p in windows.items():
                if old_p and old_p > 0:
                    diff_pct = ((current_price - old_p) / old_p) * 100

                    # Делаем индикаторы зелено/красными
                    if diff_pct > 0:
                        emoji = "🟢"
                    elif diff_pct < 0:
                        emoji = "🔴"
                    else:
                        emoji = "⚪️"

                    msg_lines.append(f"• За {w_name}: {emoji} {diff_pct:+.1f}% (от ${old_p:.2f})")

            # Выводим чистую прибыль
            msg_lines.extend([
                "➖➖➖➖➖➖",
                "💵 <b>Доход на баланс:",
                f"С учетом комиссии Steam: ~${net_price:.2f}"
            ])

            # Собираем все строки через перенос
            final_msg = "\n".join(msg_lines)

            logger.warning(f"СИГНАЛ: {title} | Триггер: {trigger_window}")
            send_biz_alert(title, final_msg)
            alerts_found += 1

        logger.info(f"Проверка завершена. Найдено и отправлено новых сигналов: {alerts_found}")

