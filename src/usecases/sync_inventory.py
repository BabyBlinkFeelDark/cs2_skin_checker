# src/usecases/sync_inventory.py
from config import logger
from steam_api import SteamClient
from repositories.inventory_repository import InventoryRepository

class SyncInventoryUseCase:
    """Сценарий: Запросить инвентарь у Steam и синхронизировать с БД (Soft Sync)."""

    def __init__(self, steam_client: SteamClient, inv_repo: InventoryRepository):
        self.steam_client = steam_client
        self.inv_repo = inv_repo

    def execute(self):
        logger.info("Запуск синхронизации инвентаря...")
        steam_items = self.steam_client.fetch_inventory()

        if steam_items is None:
            logger.error("Не удалось получить инвентарь. Синхронизация прервана.")
            return

        db_assets = self.inv_repo.get_all_asset_ids()
        steam_assets = set(item.asset_id for item in steam_items)

        # Удаляем проданное (то, что было в БД, но пропало из Steam)
        sold_assets = db_assets - steam_assets
        if sold_assets:
            self.inv_repo.delete_assets(sold_assets)
            logger.info(f"Удалено {len(sold_assets)} проданных предметов из базы.")

        # Синхронизируем оставшееся и новое (чтобы не потерять baseline_price)
        self.inv_repo.sync_items(steam_items, self.steam_client.app_id)
        logger.info(f"Инвентарь успешно синхронизирован. Актуально предметов: {len(steam_items)}.")
