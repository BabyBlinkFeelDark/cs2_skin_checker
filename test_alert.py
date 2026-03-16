# test_alert.py
import sqlite3
from pathlib import Path
import os
import sys
import time


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from src.alerts_sender import send_toast

# Определяем путь к БД
if getattr(sys, 'frozen', False):
    app_data = os.getenv('LOCALAPPDATA')
    db_path = Path(app_data) / "skin_watcher" / "app.db"
else:
    db_path = Path(__file__).resolve().parent / "data" / "app.db"


def trigger_guaranteed_drop():
    print(f"Подключаемся к БД: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Берем первый попавшийся предмет
    cursor.execute("SELECT id, market_hash_name FROM market_items LIMIT 1")
    item = cursor.fetchone()

    if not item:
        print("В базе нет предметов. Запусти main.py хотя бы раз.")
        return

    item_id, name = item[0], item[1]

    print(f"\nВыбран предмет: {name}")
    print("Удаляем старую историю для чистоты эксперимента...")
    cursor.execute("DELETE FROM price_history WHERE market_item_id = ?", (item_id,))

    # 1. Вставляем старую высокую цену (например, $100.0)
    old_price = 100.0
    print(f"Вставляем старую цену: ${old_price}")
    cursor.execute("""
        INSERT INTO price_history (market_item_id, price_real, volume, recorded_at)
        VALUES (?, ?, 0, datetime('now'))
    """, (item_id, old_price))
    conn.commit()

    # 2. Ждем ровно 2 секунды, чтобы время в БД точно отличалось!
    print("Ждем 2 секунды, чтобы временная метка сместилась...")
    time.sleep(2)

    # 3. Вставляем новую низкую цену (например, $40.0 - это падение на 60%)
    new_price = 40.0
    print(f"Вставляем новую цену: ${new_price}")
    cursor.execute("""
        INSERT INTO price_history (market_item_id, price_real, volume, recorded_at)
        VALUES (?, ?, 0, datetime('now'))
    """, (item_id, new_price))
    conn.commit()
    conn.close()

    print("\n✅ Данные вставлены. Разница во времени гарантирована.")
    print("Теперь мы напрямую вызовем метод проверки алертов!")


if __name__ == "__main__":
    trigger_guaranteed_drop()

    # Прямо отсюда запускаем проверку, чтобы не ждать полного цикла main.py
    from src.services import WatcherService

    # Заглушка SteamID, он здесь не важен, так как мы проверяем только БД
    watcher = WatcherService("76561198000000000")
    print("\n--- ЗАПУСК ПРОВЕРКИ ---")
    watcher.check_price_alerts()
    print("--- ПРОВЕРКА ЗАВЕРШЕНА ---")
