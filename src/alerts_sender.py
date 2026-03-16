import platform
import subprocess
import requests
import html
from config import logger, load_settings
from database import get_db_connection

settings = load_settings()

# Бизнес алерты
TG_BIZ_TOKEN = settings.get("telegram_biz_token", "")
TG_BIZ_CHAT_ID = settings.get("telegram_biz_chat_id", "")

# Инфо алерты
TG_INFO_TOKEN = settings.get("telegram_info_token", "")
TG_INFO_CHAT_ID = settings.get("telegram_info_chat_id", "")

PROXY_URL = ""
TG_PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from win11toast import toast
    except ImportError:
        logger.warning("Библиотека win11toast не установлена.")
        toast = None

class TelegramSender:
    def __init__(self, token: str, chat_id: str, table_name: str):
        self.token = token
        self.chat_id = chat_id
        self.table_name = table_name
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    def enqueue_message(self, title: str, text: str):
        if not self.api_url or not self.chat_id:
            return

        safe_title = html.escape(title)
        safe_text = html.escape(text)
        formatted_message = f"<b>{safe_title}</b>\n\n{safe_text}"

        try:
            with get_db_connection() as conn:
                # Прямая вставка имени таблицы безопасна, т.к. мы задаем её сами в коде
                conn.execute(
                    f"INSERT INTO {self.table_name} (message_text, status) VALUES (?, ?)",
                    (formatted_message, 'pending')
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка при записи в {self.table_name}: {e}")

    def process_queue(self):
        if not self.api_url or not self.chat_id:
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT id, message_text FROM {self.table_name} WHERE status = 'pending' ORDER BY id ASC")
                pending_messages = cursor.fetchall()

            if not pending_messages:
                return

            logger.info(f"[{self.table_name}] Склеиваем {len(pending_messages)} сообщений...")
            MAX_LEN = 4000
            batches = []
            current_text = ""
            current_ids = []

            for msg in pending_messages:
                msg_id = msg['id']
                text = msg['message_text']
                separator = "\n\n➖➖➖➖➖➖\n\n"

                if current_text and (len(current_text) + len(separator) + len(text) > MAX_LEN):
                    batches.append((current_text, current_ids))
                    current_text = text
                    current_ids = [msg_id]
                else:
                    current_text = current_text + separator + text if current_text else text
                    current_ids.append(msg_id)

            if current_text:
                batches.append((current_text, current_ids))

            for batch_text, batch_ids in batches:
                payload = {
                    "chat_id": self.chat_id,
                    "text": batch_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }

                try:
                    response = requests.post(self.api_url, json=payload, proxies=TG_PROXIES, timeout=(10, 60))

                    if response.status_code == 200:
                        with get_db_connection() as conn:
                            placeholders = ','.join('?' * len(batch_ids))
                            conn.execute(f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})", tuple(batch_ids))
                            conn.commit()
                        logger.info(f"Успешно отправлена пачка из {len(batch_ids)} сообщений!")

                    elif response.status_code == 429:
                        logger.warning("Слишком много запросов к Telegram (429). Ждем.")
                        break

                    else:
                        logger.error(f"Ошибка TG API ({response.status_code}): {response.text}")
                        if response.status_code == 400:
                            with get_db_connection() as conn:
                                placeholders = ','.join('?' * len(batch_ids))
                                conn.execute(f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})", tuple(batch_ids))
                                conn.commit()
                        continue

                except requests.exceptions.ReadTimeout:
                    logger.warning("Telegram не ответил за 60 секунд. Удаляем пачку.")
                    with get_db_connection() as conn:
                        placeholders = ','.join('?' * len(batch_ids))
                        conn.execute(f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})", tuple(batch_ids))
                        conn.commit()
                    continue
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Нет связи с сервером Telegram: {e}")
                    break
                except requests.exceptions.RequestException as e:
                    logger.error(f"Неизвестный сбой сети: {e}")
                    break

        except Exception as e:
            logger.error(f"Ошибка при обработке {self.table_name}: {e}")

tg_biz_sender = TelegramSender(TG_BIZ_TOKEN, TG_BIZ_CHAT_ID, "alert_queue_biz")
tg_info_sender = TelegramSender(TG_INFO_TOKEN, TG_INFO_CHAT_ID, "alert_queue_info")

def _show_desktop_toast(title: str, body: str):
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

def send_biz_alert(title: str, body: str):
    logger.info(f"[БИЗНЕС АЛЕРТ] {title} | {body}")
    _show_desktop_toast(title, body)
    tg_biz_sender.enqueue_message(title, body)

def send_info_alert(title: str, body: str):
    logger.info(f"[ИНФО АЛЕРТ] {title} | {body}")
    # _show_desktop_toast(title, body) # Раскомментируй, если хочешь получать Windows уведомления даже для инфо-алертов
    tg_info_sender.enqueue_message(title, body)
