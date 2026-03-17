# test_alert.py
import sqlite3
from pathlib import Path
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

# Определяем путь к БД
if getattr(sys, 'frozen', False):
    app_data = os.getenv('LOCALAPPDATA')
    db_path = Path(app_data) / "skin_watcher" / "app.db"
else:
    db_path = Path(__file__).resolve().parent / "data" / "app.db"


def inject_time_travel_data():
    print(f"Подключаемся к БД: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # БЕРЕМ ПРЕДМЕТ СТРОГО ИЗ ИНВЕНТАРЯ (иначе скрипт его проигнорирует)
    cursor.execute("""
        SELECT m.id, m.market_hash_name 
        FROM market_items m
        JOIN inventory_assets i ON m.id = i.market_item_id
        LIMIT 1
    """)
    item = cursor.fetchone()

    if not item:
        print("❌ В базе нет инвентаря. Сначала запусти main.py хотя бы один раз, чтобы парсер собрал твои скины.")
        return False

    item_id, name = item[0], item[1]
    print(f"\n🎯 Выбран предмет для теста: {name}")

    print("🧹 Очищаем старую историю и кулдауны для чистоты эксперимента...")
    cursor.execute("DELETE FROM price_history WHERE market_item_id = ?", (item_id,))
    cursor.execute("DELETE FROM alert_history WHERE market_item_id = ?", (item_id,))

    # 1. ЗАДАЕМ БАЗОВУЮ ЦЕНУ (Точку входа)
    baseline = 10.0
    print(f"📥 Задаем базовую цену (Baseline): ${baseline}")
    cursor.execute("""
        UPDATE inventory_assets 
        SET baseline_price = ? 
        WHERE market_item_id = ?
    """, (baseline, item_id))

    # 2. ЦЕНА НЕДЕЛЮ НАЗАД (-8 дней, чтобы точно попасть в окно >7d)
    price_7d = 12.0
    print(f"📅 Вставляем цену за прошлую неделю: ${price_7d}")
    cursor.execute("""
        INSERT INTO price_history (market_item_id, price_real, volume, recorded_at)
        VALUES (?, ?, 100, datetime('now', '-8 days'))
    """, (item_id, price_7d))

    # 3. ЦЕНА ВЧЕРА (-25 часов, чтобы точно попасть в окно >24h)
    price_24h = 15.0
    print(f"🕒 Вставляем вчерашнюю цену: ${price_24h}")
    cursor.execute("""
        INSERT INTO price_history (market_item_id, price_real, volume, recorded_at)
        VALUES (?, ?, 100, datetime('now', '-25 hours'))
    """, (item_id, price_24h))

    # 4. ТЕКУЩАЯ ЦЕНА (Свежий памп)
    current_price = 25.0
    print(f"🚀 Вставляем ТЕКУЩУЮ цену (ПАМП): ${current_price}")
    cursor.execute("""
        INSERT INTO price_history (market_item_id, price_real, volume, recorded_at)
        VALUES (?, ?, 500, datetime('now'))
    """, (item_id, current_price))

    conn.commit()
    conn.close()

    print("\n✅ Данные успешно подменены (Машина времени сработала).")
    return True


if __name__ == "__main__":
    success = inject_time_travel_data()

    if success:
        from src.services import WatcherService
        from src.alerts_sender import tg_biz_sender, tg_info_sender

        # Инициализируем сервис (с порогом роста в 25%)
        watcher = WatcherService("76561198000000000", rise_threshold=25.0, drop_threshold=25.0)

        print("\n--- 🔍 ЗАПУСК ПРОВЕРКИ АЛЕРТОВ ---")
        watcher.check_price_alerts()
        print("--- 🏁 ПРОВЕРКА ЗАВЕРШЕНА ---")

        print("\n--- 📤 ЗАПУСК ОТПРАВКИ ОЧЕРЕДЕЙ В ТЕЛЕГРАМ ---")
        while True:
            tg_biz_sender.process_queue()
            tg_info_sender.process_queue()

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM alert_queue_biz WHERE status = 'pending'")
                count_biz = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM alert_queue_info WHERE status = 'pending'")
                count_info = cursor.fetchone()[0]

                total_count = count_biz + count_info
            except sqlite3.OperationalError:
                total_count = 0
            finally:
                conn.close()

            if total_count == 0:
                print("✅ Обе очереди пусты! Все сообщения успешно доставлены.")
                break
            else:
                print(f"⏳ Осталось сообщений (Бизнес: {count_biz}, Инфо: {count_info}). Ждем 5 сек...")
                time.sleep(5)
