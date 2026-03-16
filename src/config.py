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


# --- НОВАЯ ЛОГИКА НАСТРОЕК В config.py ---
def load_settings():
    """Загружает настройки из JSON. Если файла нет - просит пользователя ввести данные."""
    default_settings = {
        "steam_id_64": "",
        "drop_threshold_percent": 30.0,
        "rise_threshold_percent": 25.0,
        "check_interval_hours": 1,
        "telegram_token": "",  # Новое поле для Telegram API
        "telegram_chat_id": ""  # Новое поле для Telegram ID
    }

    if not SETTINGS_PATH.exists():
        print("\n=== Добро пожаловать в Skin Watcher! ===")
        print("Похоже, это первый запуск. Нам нужно настроить ваш профиль.\n")

        # Запрашиваем SteamID
        while True:
            steam_id = input("Введите ваш SteamID64 (17 цифр): ").strip()
            if len(steam_id) == 17 and steam_id.isdigit():
                default_settings["steam_id_64"] = steam_id
                break
            else:
                print("Ошибка: SteamID64 должен состоять ровно из 17 цифр.")

        print("\n--- Настройка Telegram (Опционально) ---")
        print("Если вы не хотите использовать Telegram-бота, просто нажмите Enter два раза.")
        tg_token = input("Введите токен Telegram-бота от @BotFather (или Enter для пропуска): ").strip()
        tg_chat = input("Введите ваш личный Chat ID от @userinfobot (или Enter для пропуска): ").strip()

        if tg_token and tg_chat:
            default_settings["telegram_token"] = tg_token
            default_settings["telegram_chat_id"] = tg_chat
            print("Telegram-уведомления включены!")
        else:
            print("Telegram-уведомления отключены. Будут использоваться системные уведомления Windows/Linux.")

        # Сохраняем в файл
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(default_settings, f, indent=4)
        print(f"\nНастройки успешно сохранены в: {SETTINGS_PATH}\n")

        return default_settings

    # Если файл есть - просто читаем его
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)

            # На случай, если файл старой версии, добавим в него новые ключи (Backward compatibility)
            needs_update = False
            if "telegram_token" not in settings:
                settings["telegram_token"] = ""
                needs_update = True
            if "telegram_chat_id" not in settings:
                settings["telegram_chat_id"] = ""
                needs_update = True

            if needs_update:
                with open(SETTINGS_PATH, "w", encoding="utf-8") as fw:
                    json.dump(settings, fw, indent=4)

            return settings

    except Exception as e:
        logger.error(f"Ошибка чтения settings.json: {e}")
        return default_settings


