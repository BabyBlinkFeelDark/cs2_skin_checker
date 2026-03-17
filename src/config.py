# src/config.py
import os
import sys
import logging
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
# Путь к старому JSON (оставляем только для разовой миграции)
LEGACY_SETTINGS_PATH = BASE_DIR / "settings.json"


def setup_logging():
    logger = logging.getLogger("skin_watcher")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)

    # Чтобы логгер не дублировал сообщения, если он инициализируется дважды
    if not logger.handlers:
        logger.addHandler(handler)
        if not getattr(sys, 'frozen', False):
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            logger.addHandler(console)

    return logger


logger = setup_logging()
