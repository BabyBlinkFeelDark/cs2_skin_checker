# # src/services.py
# import time
# import random
# from config import logger
# from steam_api import SteamClient
# from alerts_sender import send_biz_alert
# from domain.models import AlertEvent
# from repositories.inventory_repository import InventoryRepository
# from repositories.price_repository import PriceRepository
#
#
# class WatcherService:
#     def __init__(self, steam_id, drop_threshold=30.0, rise_threshold=25.0, min_diff_dollars: float = 0.5,
#                  proxy_url=None):
#         self.steam_client = SteamClient(steam_id, proxy_url=proxy_url)
#         self.drop_threshold = drop_threshold
#         self.rise_threshold = rise_threshold
#         self.min_diff_dollars = min_diff_dollars
#
#         # Инициализируем репозитории
#         self.inv_repo = InventoryRepository()
#         self.price_repo = PriceRepository()
#
#     def sync_inventory(self):
#         """Синхронизирует инвентарь пользователя (Soft Sync)."""
#         logger.info("Запуск синхронизации инвентаря...")
#         steam_items = self.steam_client.fetch_inventory()
#
#         if steam_items is None:
#             logger.error("Не удалось получить инвентарь. Синхронизация прервана.")
#             return
#
#         db_assets = self.inv_repo.get_all_asset_ids()
#         steam_assets = set(item.asset_id for item in steam_items)
#
#         # Удаляем проданное
#         sold_assets = db_assets - steam_assets
#         if sold_assets:
#             self.inv_repo.delete_assets(sold_assets)
#             logger.info(f"Удалено {len(sold_assets)} проданных предметов из базы.")
#
#         # Синхронизируем оставшееся и новое
#         self.inv_repo.sync_items(steam_items, self.steam_client.app_id)
#         logger.info(f"Инвентарь успешно синхронизирован. Актуально предметов: {len(steam_items)}.")
#
#     def refresh_prices(self):
#         """Обновляет цены и фиксирует точку входа."""
#         logger.info("Запуск обновления цен...")
#         items_to_check = self.inv_repo.get_unique_market_items()
#
#         if not items_to_check:
#             logger.info("Нет предметов для обновления цен.")
#             return
#
#         success_count = 0
#         for item in items_to_check:
#             market_item_id = item['id']
#             market_hash_name = item['market_hash_name']
#
#             price_record = self.steam_client.fetch_price(market_hash_name)
#
#             if price_record:
#                 price_record.market_item_id = market_item_id
#
#                 # Записываем историю
#                 self.price_repo.add_price_record(price_record)
#
#                 # Фиксируем точку входа для новых предметов
#                 self.inv_repo.set_baseline_price(market_item_id, price_record.price)
#
#                 success_count += 1
#                 logger.info(f"Обновлена цена: {market_hash_name} -> ${price_record.price}")
#
#             # Рандомная задержка от бана
#             sleep_time = random.uniform(3.0, 6.0)
#             time.sleep(sleep_time)
#
#         logger.info(f"Обновление цен завершено. Успешно: {success_count}/{len(items_to_check)}.")
#
#     def check_price_alerts(self):
#         """Проверяет цены по окнам и отправляет карточки."""
#         logger.info("Проверка сигналов изменения цены...")
#
#         items = self.price_repo.get_price_windows()
#         alerts_found = 0
#
#         for item in items:
#             current_price = item['current_price']
#             if not current_price:
#                 continue
#
#             windows = {
#                 '24ч': item['price_24h'],
#                 '7дн': item['price_7d'],
#                 'Точка входа': item['baseline_price']
#             }
#
#             trigger_window, trigger_direction, trigger_change = None, None, 0.0
#
#             for window_name, old_price in windows.items():
#                 if not old_price or old_price <= 0:
#                     continue
#
#                 if abs(current_price - old_price) < self.min_diff_dollars:
#                     continue
#
#                 percent_change = ((current_price - old_price) / old_price) * 100
#
#                 direction = None
#                 if percent_change <= -self.drop_threshold:
#                     direction = 'drop'
#                 elif percent_change >= self.rise_threshold:
#                     direction = 'rise'
#
#                 if direction:
#                     trigger_window = window_name
#                     trigger_direction = direction
#                     trigger_change = percent_change
#                     break
#
#             if not trigger_direction:
#                 continue
#
#             # Анти-спам
#             event = AlertEvent(item['market_item_id'], trigger_window, trigger_direction)
#             if self.price_repo.has_recent_alert(event):
#                 continue
#
#             self.price_repo.log_alert_event(event)
#
#             # Формирование карточки
#             net_price = current_price / 1.15
#             title_emoji = "📈 ВЗЛЕТ" if trigger_direction == 'rise' else "📉 ПАДЕНИЕ"
#             title = f"{title_emoji}: {item['market_hash_name']}"
#
#             msg_lines = [
#                 f"⚡ Триггер: {trigger_window} ({trigger_change:+.1f}%)",
#                 f"💰 Текущая цена: ${current_price:.2f}",
#                 "➖➖➖➖➖➖",
#                 "📊 Динамика:"
#             ]
#
#             for w_name, old_p in windows.items():
#                 if old_p and old_p > 0:
#                     diff_pct = ((current_price - old_p) / old_p) * 100
#                     emoji = "🟢" if diff_pct > 0 else "🔴" if diff_pct < 0 else "⚪️"
#                     msg_lines.append(f"• За {w_name}: {emoji} {diff_pct:+.1f}% (от ${old_p:.2f})")
#
#             msg_lines.extend([
#                 "➖➖➖➖➖➖",
#                 "💵 <b>Доход на баланс:</b>",
#                 f"С учетом комиссии Steam: ~${net_price:.2f}"
#             ])
#
#             send_biz_alert(title, "\n".join(msg_lines))
#             alerts_found += 1
#
#         logger.info(f"Проверка завершена. Отправлено сигналов: {alerts_found}")
