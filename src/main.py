# src/main.py
import time
import schedule

from config import logger
from settings_manager import load_settings
from database import init_db

# Инфраструктура
from steam_api import SteamClient
from alerts_sender import send_info_alert, tg_biz_sender, tg_info_sender

# Репозитории
from repositories.inventory_repository import InventoryRepository
from repositories.price_repository import PriceRepository
from repositories.queue_repository import QueueRepository

# Бизнес-сценарии (Use Cases)
from usecases.sync_inventory import SyncInventoryUseCase
from usecases.sync_prices import UpdatePricesUseCase
from usecases.analyze_alerts import AnalyzeAlertsUseCase

PROXY_URL = None


def run_pipeline(
        sync_uc: SyncInventoryUseCase,
        prices_uc: UpdatePricesUseCase,
        alerts_uc: AnalyzeAlertsUseCase
):
    """Единый цикл работы приложения (Pipeline)."""

    # 1. Получаем размеры очередей (используя новый QueueRepository)
    biz_repo = QueueRepository("alert_queue_biz")
    info_repo = QueueRepository("alert_queue_info")
    biz_before, info_before = biz_repo.get_count(), info_repo.get_count()

    logger.info(f"=== Плановое обновление (Очереди: Бизнес={biz_before}, Инфо={info_before}) ===")

    # 2. Выполняем бизнес-сценарии строго по порядку
    sync_uc.execute()
    prices_uc.execute()
    alerts_uc.execute()

    # 3. Отправляем накопившиеся сообщения
    tg_biz_sender.process_queue()
    tg_info_sender.process_queue()

    biz_after, info_after = biz_repo.get_count(), info_repo.get_count()
    logger.info(f"=== Обновление завершено. Осталось в очереди: Бизнес={biz_after}, Инфо={info_after} ===")


def main():
    logger.info("=== Запуск Skin Watcher ===")

    # 1. Инициализация БД и миграции
    init_db()

    # 2. Загрузка настроек из БД
    settings = load_settings()

    steam_id = settings.get("steam_id_64")
    drop_thresh = float(settings.get("drop_threshold_percent", 30.0))
    rise_thresh = float(settings.get("rise_threshold_percent", 25.0))
    interval_hours = int(settings.get("check_interval_hours", 1))
    min_diff = float(settings.get("min_difference_dollars", 0.5))

    if not steam_id:
        logger.critical("SteamID не задан в базе настроек. Завершение работы.")
        return

    # --- СБОРКА ЗАВИСИМОСТЕЙ (Dependency Injection) ---

    # Репозитории
    inv_repo = InventoryRepository()
    price_repo = PriceRepository()

    # API Клиент
    steam_client = SteamClient(steam_id=steam_id, proxy_url=PROXY_URL)

    # Сценарии (Use Cases)
    sync_inventory_uc = SyncInventoryUseCase(
        steam_client=steam_client,
        inv_repo=inv_repo
    )

    update_prices_uc = UpdatePricesUseCase(
        steam_client=steam_client,
        inv_repo=inv_repo,
        price_repo=price_repo,
        ignore_items_below_dollars=0.10  # Наш новый порог отсечения мусора
    )

    analyze_alerts_uc = AnalyzeAlertsUseCase(
        price_repo=price_repo,
        drop_threshold=drop_thresh,
        rise_threshold=rise_thresh,
        min_diff_dollars=min_diff,
        min_healthy_volume=5  # Защита от фейковых пампов
    )

    # ---------------------------------------------------

    send_info_alert("Skin Watcher", "Служба мониторинга цен запущена в фоне")

    # Первый прогон при старте
    run_pipeline(sync_inventory_uc, update_prices_uc, analyze_alerts_uc)

    # Настройка планировщика
    schedule.every(interval_hours).hours.do(
        run_pipeline, sync_inventory_uc, update_prices_uc, analyze_alerts_uc
    )

    # Проверка очередей каждые 5 минут
    schedule.every(5).minutes.do(tg_biz_sender.process_queue)
    schedule.every(5).minutes.do(tg_info_sender.process_queue)

    logger.info("Переход в режим ожидания (фоновый цикл)...")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        send_info_alert("Skin Watcher: Ошибка", "Процесс аварийно завершен. Проверь логи.")
