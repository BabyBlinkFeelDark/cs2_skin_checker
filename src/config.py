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


def load_settings():
    default_settings = {
        "steam_id_64": "",
        "drop_threshold_percent": 30.0,
        "rise_threshold_percent": 25.0,
        "check_interval_hours": 1,
        "min_difference_dollars": 0.5,
        "telegram_biz_token": "",  # Для цен
        "telegram_biz_chat_id": "",
        "telegram_info_token": "",  # Для системных логов
        "telegram_info_chat_id": ""
    }

    if not SETTINGS_PATH.exists():
        print("\n=== Добро пожаловать в Skin Watcher! ===")
        print("Похоже, это первый запуск. Нам нужно настроить ваш профиль.\n")

        while True:
            steam_id = input("Введите ваш SteamID64 (17 цифр): ").strip()
            if len(steam_id) == 17 and steam_id.isdigit():
                default_settings["steam_id_64"] = steam_id
                break
            else:
                print("Ошибка: SteamID64 должен состоять ровно из 17 цифр.")

        print("\n--- Бот для БИЗНЕС-АЛЕРТОВ (Рост/Падение цен) ---")
        default_settings["telegram_biz_token"] = input("Введите токен Telegram-бота: ").strip()
        default_settings["telegram_biz_chat_id"] = input("Введите ваш Chat ID: ").strip()

        print("\n--- Бот для ИНФО-АЛЕРТОВ (Старт/Краши/Ошибки) ---")
        print("Можно оставить пустым, если инфо-алерты не нужны.")
        default_settings["telegram_info_token"] = input("Введите токен инфо-бота: ").strip()
        default_settings["telegram_info_chat_id"] = input("Введите Chat ID для инфо-бота: ").strip()

        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(default_settings, f, indent=4)
        print(f"\nНастройки успешно сохранены в: {SETTINGS_PATH}\n")
        return default_settings

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)

            needs_update = False
            # Обратная совместимость (перенос старого токена в biz)
            if "telegram_token" in settings:
                settings["telegram_biz_token"] = settings.pop("telegram_token")
                settings["telegram_biz_chat_id"] = settings.pop("telegram_chat_id", "")
                needs_update = True

            if "telegram_info_token" not in settings:
                settings["telegram_info_token"] = ""
                settings["telegram_info_chat_id"] = ""
                needs_update = True

            if "min_difference_dollars" not in settings:
                settings["min_difference_dollars"] = 0.5
                needs_update = True

            if needs_update:
                with open(SETTINGS_PATH, "w", encoding="utf-8") as fw:
                    json.dump(settings, fw, indent=4)

            return settings

    except Exception as e:
        logger.error(f"Ошибка чтения settings.json: {e}")
        return default_settings
