import time
import schedule
from config import logger, load_settings
from database import init_db, get_db_connection
from services import WatcherService
from alerts_sender import send_info_alert, tg_biz_sender, tg_info_sender

PROXY_URL = None


def get_queue_sizes() -> tuple:
    """Возвращает кол-во неотправленных сообщений (бизнес, инфо)."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM alert_queue_biz WHERE status = 'pending'")
            biz_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM alert_queue_info WHERE status = 'pending'")
            info_count = cursor.fetchone()[0]
            return biz_count, info_count
    except Exception as e:
        logger.error(f"Ошибка при проверке размера очередей: {e}")
        return 0, 0


def job_update_data(watcher: WatcherService):
    biz_before, info_before = get_queue_sizes()
    logger.info(f"=== Плановое обновление (Очереди: Бизнес={biz_before}, Инфо={info_before}) ===")

    watcher.sync_inventory()
    watcher.refresh_prices()
    watcher.check_price_alerts()

    # Пытаемся отправить обе очереди
    tg_biz_sender.process_queue()
    tg_info_sender.process_queue()

    biz_after, info_after = get_queue_sizes()
    logger.info(f"=== Обновление завершено. Осталось в очереди: Бизнес={biz_after}, Инфо={info_after} ===")


def main():
    logger.info("=== Запуск Skin Watcher ===")
    init_db()
    settings = load_settings()

    steam_id = settings.get("steam_id_64")
    drop_thresh = settings.get("drop_threshold_percent", 10.0)
    rise_thresh = settings.get("rise_threshold_percent", 10.0)
    interval_hours = settings.get("check_interval_hours", 1)
    min_diff = settings.get("min_difference_dollars", 0.5)

    if not steam_id:
        logger.critical("SteamID не задан в настройках. Завершение работы.")
        return

    watcher = WatcherService(
        steam_id=steam_id,
        drop_threshold=drop_thresh,
        rise_threshold=rise_thresh,
        min_diff_dollars=min_diff,
        proxy_url=PROXY_URL
    )

    # Инфо-алерт при старте программы
    send_info_alert("Skin Watcher", "Служба мониторинга цен запущена в фоне")

    job_update_data(watcher)

    schedule.every(interval_hours).hours.do(job_update_data, watcher)

    # Проверяем обе очереди каждые 5 минут
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
        # Инфо-алерт при падении
        send_info_alert("Skin Watcher: Ошибка", "Процесс аварийно завершен. Проверь логи.")
