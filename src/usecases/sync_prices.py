# src/usecases/sync_prices.py
import time
import random
from config import logger
from steam_api import SteamClient
from repositories.inventory_repository import InventoryRepository
from repositories.price_repository import PriceRepository


class UpdatePricesUseCase:
    """Сценарий: Запросить актуальные цены для инвентаря у Steam API."""

    def __init__(
            self,
            steam_client: SteamClient,
            inv_repo: InventoryRepository,
            price_repo: PriceRepository,
            ignore_items_below_dollars: float = 0.10  # Защита от мусора
    ):
        self.steam_client = steam_client
        self.inv_repo = inv_repo
        self.price_repo = price_repo
        self.ignore_threshold = ignore_items_below_dollars

    def execute(self):
        logger.info("Запуск обновления цен...")

        # Достаем все уникальные предметы и их последнюю цену
        items_to_check = self.price_repo.get_items_with_latest_price()

        if not items_to_check:
            logger.info("Нет предметов для обновления цен.")
            return

        success_count = 0
        skipped_count = 0

        for item in items_to_check:
            market_item_id = item['id']
            market_hash_name = item['market_hash_name']
            latest_known_price = item['latest_price']

            # --- ИГНОР МУСОРА ---
            if latest_known_price is not None and latest_known_price < self.ignore_threshold:
                logger.debug(f"Игнор мусора: {market_hash_name} (${latest_known_price})")
                skipped_count += 1
                continue

            price_record = self.steam_client.fetch_price(market_hash_name)

            if price_record:
                price_record.market_item_id = market_item_id

                # Пишем историю
                self.price_repo.add_price_record(price_record)

                # Фиксируем точку входа (если это первая цена)
                self.inv_repo.set_baseline_price(market_item_id, price_record.price)

                success_count += 1
                logger.info(f"Обновлена цена: {market_hash_name} -> ${price_record.price}")

            # Рандомная задержка (Спим только если был HTTP-запрос)
            sleep_time = random.uniform(3.0, 6.0)
            time.sleep(sleep_time)

        logger.info(f"Обновление цен завершено. Успешно: {success_count}. Пропущено мусора: {skipped_count}.")
