# src/main.py
import time
import schedule
# Импортируем нашу функцию load_settings
from config import logger, load_settings
from database import init_db
from services import WatcherService
from alerts_sender import send_toast

PROXY_URL = None


def job_update_data(watcher: WatcherService):
    logger.info("=== Запуск планового обновления ===")
    watcher.sync_inventory()
    watcher.refresh_prices()
    watcher.check_price_alerts()
    send_toast("Skin Watcher", "Цены на инвентарь успешно обновлены и проверены!")
    logger.info("=== Плановое обновление завершено ===")


def main():
    logger.info("=== Запуск Skin Watcher ===")
    init_db()

    # 1. ЗАГРУЖАЕМ НАСТРОЙКИ (Или спрашиваем у юзера, если их нет)
    settings = load_settings()

    steam_id = settings.get("steam_id_64")
    drop_thresh = settings.get("drop_threshold_percent", 30.0)
    rise_thresh = settings.get("rise_threshold_percent", 25.0)
    interval_hours = settings.get("check_interval_hours", 4)

    if not steam_id:
        logger.critical("SteamID не задан в настройках. Завершение работы.")
        return

    # 2. ПЕРЕДАЕМ НАСТРОЙКИ В СЕРВИС
    watcher = WatcherService(
        steam_id=steam_id,
        drop_threshold=drop_thresh,
        rise_threshold=rise_thresh,
        proxy_url=PROXY_URL
    )

    send_toast("Skin Watcher", "Служба мониторинга цен запущена в фоне")

    job_update_data(watcher)

    # 3. УСТАНАВЛИВАЕМ РАСПИСАНИЕ ИЗ ФАЙЛА
    schedule.every(interval_hours).hours.do(job_update_data, watcher)

    logger.info("Переход в режим ожидания (фоновый цикл)...")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        send_toast("Skin Watcher: Ошибка", "Процесс аварийно завершен. Проверь логи.")
