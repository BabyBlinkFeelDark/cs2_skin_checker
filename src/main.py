# src/main.py
import time
import schedule
from config import logger, load_settings
from database import init_db, get_db_connection
from services import WatcherService
from alerts_sender import send_toast, tg_sender

PROXY_URL = None


def get_queue_size() -> int:
    """Возвращает количество неотправленных сообщений в очереди."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM alert_queue WHERE status = 'pending'")
            return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Ошибка при проверке размера очереди: {e}")
        return 0


def job_update_data(watcher: WatcherService):
    # Проверяем очередь ДО обновления
    queue_before = get_queue_size()
    logger.info(f"=== Запуск планового обновления (в очереди сообщений: {queue_before}) ===")

    watcher.sync_inventory()
    watcher.refresh_prices()
    watcher.check_price_alerts()
    # send_toast("Skin Watcher", "Цены на инвентарь успешно обновлены и проверены!")

    # Сразу пытаемся отправить, если что-то есть
    tg_sender.process_queue()

    # Проверяем очередь ПОСЛЕ отправки
    queue_after = get_queue_size()
    logger.info(f"=== Плановое обновление завершено. Осталось в очереди: {queue_after} ===")


def main():
    logger.info("=== Запуск Skin Watcher ===")
    init_db()

    settings = load_settings()

    steam_id = settings.get("steam_id_64")
    drop_thresh = settings.get("drop_threshold_percent", 10.0)
    rise_thresh = settings.get("rise_threshold_percent", 10.0)
    interval_hours = settings.get("check_interval_hours", 1)

    # НОВАЯ НАСТРОЙКА: минимальный шаг изменения цены в долларах (по умолчанию $0.50)
    min_diff = settings.get("min_difference_dollars", 0.5)

    if not steam_id:
        logger.critical("SteamID не задан в настройках. Завершение работы.")
        return

    watcher = WatcherService(
        steam_id=steam_id,
        drop_threshold=drop_thresh,
        rise_threshold=rise_thresh,
        min_diff_dollars=min_diff,  # <--- Передаем сюда
        proxy_url=PROXY_URL
    )

    # send_toast("Skin Watcher", "Служба мониторинга цен запущена в фоне")

    job_update_data(watcher)

    # 1. Запуск основной работы (Парсинг + Проверка) раз в N часов
    schedule.every(interval_hours).hours.do(job_update_data, watcher)

    # 2. Почтальон: проверка очереди каждые 5 минут (если сеть падала)
    schedule.every(5).minutes.do(tg_sender.process_queue)

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
