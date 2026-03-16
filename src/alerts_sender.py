# /home/babyblinkfeeldark/skin_watcher/src/alerts_sender.py
import platform
import subprocess
from config import logger

# Проверяем, на какой ОС мы сейчас находимся
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from win11toast import toast
    except ImportError:
        logger.warning("Библиотека win11toast не установлена, уведомления будут только в логе.")
        toast = None0


def send_toast(title: str, body: str):
    """Отправляет уведомление в зависимости от операционной системы."""
    logger.info(f"[УВЕДОМЛЕНИЕ] {title} | {body}")

    if IS_WINDOWS and 'toast' in globals() and toast:
        try:
            toast(title, body, app_id="Skin Watcher", audio={'silent': False})
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления Windows: {e}")
    else:
        # Резервный вариант для Linux (использует системный notify-send)
        try:
            # На Linux Mint/Ubuntu это вызовет стандартное системное всплывающее окно
            subprocess.run(['notify-send', title, body], check=False)
        except Exception as e:
            # Если notify-send не установлен, мы уже записали всё в лог выше
            logger.debug(f"Не удалось отправить notify-send (Linux): {e}")
