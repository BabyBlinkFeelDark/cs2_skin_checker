# src/infrastructure/notifications.py
import requests
import html
import platform
import subprocess
from typing import Optional
from config import logger

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    try:
        from win11toast import toast
    except ImportError:
        toast = None

class TelegramClient:
    """Только HTTP-логика. Никакой базы данных."""
    MAX_LEN = 4000

    def __init__(self, token: str, chat_id: str, proxy_url: Optional[str] = None):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None
        self.proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def format_message(self, title: str, text: str) -> str:
        safe_title = html.escape(title)
        safe_text = html.escape(text)
        return f"<b>{safe_title}</b>\n\n{safe_text}"

    def send_batch(self, combined_text: str) -> bool:
        """Возвращает True если успешно (или если это 400 Bad Request, чтобы удалить кривое сообщение)."""
        if not self.is_configured():
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": combined_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            response = requests.post(self.api_url, json=payload, proxies=self.proxies, timeout=(10, 60))
            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                logger.warning("Слишком много запросов к Telegram (429). Ждем.")
                return False
            elif response.status_code == 400:
                logger.error(f"Ошибка 400 TG API (Кривой HTML?). Удаляем пачку. Текст ответа: {response.text}")
                return True # Возвращаем True, чтобы репозиторий удалил битый HTML
            else:
                logger.error(f"Ошибка TG API ({response.status_code}): {response.text}")
                return False

        except requests.exceptions.ReadTimeout:
            logger.warning("Telegram не ответил за 60 секунд (ReadTimeout). Скорее всего доставлено.")
            return True # Удаляем
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Нет связи с сервером Telegram: {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Неизвестный сбой сети Telegram: {e}")
            return False

def show_desktop_toast(title: str, body: str):
    """Нативные уведомления OS."""
    if IS_WINDOWS and 'toast' in globals() and toast:
        try:
            toast(title, body, app_id="Skin Watcher", audio={'silent': False})
        except Exception:
            pass
    elif not IS_WINDOWS:
        try:
            subprocess.run(['notify-send', title, body], check=False)
        except Exception:
            pass
