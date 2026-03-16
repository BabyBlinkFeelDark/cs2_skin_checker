# src/config.py
import os
import sys
import logging
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path

if getattr(sys, 'frozen', False):
    app_data = os.getenv('LOCALAPPDATA')
    BASE_DIR = Path(app_data) / "skin_watcher"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent / "data"

BASE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = BASE_DIR / "app.db"
LOG_PATH = BASE_DIR / "app.log"
# ДОБАВЛЯЕМ ПУТЬ К ФАЙЛУ НАСТРОЕК
SETTINGS_PATH = BASE_DIR / "settings.json"


def setup_logging():
    logger = logging.getLogger("skin_watcher")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)
    if not getattr(sys, 'frozen', False):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger


logger = setup_logging()


# --- НОВАЯ ЛОГИКА НАСТРОЕК ---
def load_settings():
    """Загружает настройки из JSON. Если файла нет - просит пользователя ввести данные."""
    default_settings = {
        "steam_id_64": "",
        "drop_threshold_percent": 30.0,
        "rise_threshold_percent": 25.0,
        "check_interval_hours": 4
    }

    if not SETTINGS_PATH.exists():
        print("Добро пожаловать в Skin Watcher!")
        print("Похоже, это первый запуск. Нам нужно настроить ваш профиль.")

        # Запрашиваем ID у пользователя
        while True:
            steam_id = input("Введите ваш SteamID64 (17 цифр): ").strip()
            if len(steam_id) == 17 and steam_id.isdigit():
                default_settings["steam_id_64"] = steam_id
                break
            else:
                print("Ошибка: SteamID64 должен состоять ровно из 17 цифр.")

        # Сохраняем в файл
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(default_settings, f, indent=4)
        print(f"Настройки сохранены в: {SETTINGS_PATH}\n")
        return default_settings

    # Если файл есть - просто читаем его
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения settings.json: {e}")
        return default_settings
