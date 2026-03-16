# src/alerts_sender.py
import platform
import subprocess
import requests
import html
from config import logger, load_settings
from database import get_db_connection

settings = load_settings()
TELEGRAM_TOKEN = settings.get("telegram_token", "")
TELEGRAM_CHAT_ID = settings.get("telegram_chat_id", "")

# ПРОКСИ ДЛЯ ТЕЛЕГРАМА (если в РФ)
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
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def enqueue_message(self, title: str, text: str):
        """Кладет сообщение в базу данных (очередь), а не отправляет сразу."""
        if not self.token or not self.chat_id:
            return

        safe_title = html.escape(title)
        safe_text = html.escape(text)
        formatted_message = f"<b>{safe_title}</b>\n\n{safe_text}"

        try:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO alert_queue (message_text, status) VALUES (?, ?)",
                    (formatted_message, 'pending')
                )
                conn.commit()
            logger.debug("Алерт добавлен в Telegram-очередь.")
        except Exception as e:
            logger.error(f"Ошибка при записи в очередь БД: {e}")

    def process_queue(self):
        """Пытается отправить все накопившиеся сообщения из очереди пачками."""
        if not self.token or not self.chat_id:
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, message_text FROM alert_queue WHERE status = 'pending' ORDER BY id ASC")
                pending_messages = cursor.fetchall()

            if not pending_messages:
                return

            logger.info(f"Найдено {len(pending_messages)} сообщений. Склеиваем для массовой отправки...")

            # Максимальная длина сообщения в Telegram - 4096 символов. Берем с запасом 4000.
            MAX_LEN = 4000

            batches = []
            current_text = ""
            current_ids = []

            # Группируем сообщения в пачки
            for msg in pending_messages:
                msg_id = msg['id']
                text = msg['message_text']
                separator = "\n\n➖➖➖➖➖➖\n\n"

                # Если добавление текста превысит лимит, сохраняем текущую пачку и начинаем новую
                if current_text and (len(current_text) + len(separator) + len(text) > MAX_LEN):
                    batches.append((current_text, current_ids))
                    current_text = text
                    current_ids = [msg_id]
                else:
                    if current_text:
                        current_text += separator + text
                    else:
                        current_text = text
                    current_ids.append(msg_id)

            if current_text:
                batches.append((current_text, current_ids))

            # Отправляем сформированные пачки
            for batch_text, batch_ids in batches:
                payload = {
                    "chat_id": self.chat_id,
                    "text": batch_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }

                try:
                    # Увеличиваем read timeout до 60 секунд
                    response = requests.post(self.api_url, json=payload, proxies=TG_PROXIES, timeout=(10, 60))

                    if response.status_code == 200:
                        # Успех! Удаляем сразу всю отправленную пачку по их ID одним запросом
                        with get_db_connection() as conn:
                            placeholders = ','.join('?' * len(batch_ids))
                            conn.execute(f"DELETE FROM alert_queue WHERE id IN ({placeholders})", tuple(batch_ids))
                            conn.commit()
                        logger.info(f"Успешно отправлена пачка из {len(batch_ids)} сообщений одним запросом!")

                    elif response.status_code == 429:
                        logger.warning("Слишком много запросов к Telegram (429). Ждем следующего цикла.")
                        break  # Прерываем отправку оставшихся пачек

                    else:
                        logger.error(f"Ошибка TG API ({response.status_code}): {response.text}")
                        # Если словили ошибку 400 (например, кривой HTML), удаляем пачку, чтобы не застопорить очередь навсегда
                        if response.status_code == 400:
                            with get_db_connection() as conn:
                                placeholders = ','.join('?' * len(batch_ids))
                                conn.execute(f"DELETE FROM alert_queue WHERE id IN ({placeholders})", tuple(batch_ids))
                                conn.commit()
                        continue

                except requests.exceptions.ReadTimeout:
                    # Запрос ушел, но Telegram слишком долго отвечал. Сообщение, скорее всего, доставлено.
                    logger.warning(
                        "Telegram не ответил за 60 секунд (ReadTimeout). Удаляем пачку во избежание спама дублями.")
                    with get_db_connection() as conn:
                        placeholders = ','.join('?' * len(batch_ids))
                        conn.execute(f"DELETE FROM alert_queue WHERE id IN ({placeholders})", tuple(batch_ids))
                        conn.commit()
                    continue  # Пробуем отправить следующую пачку, не прерывая цикл

                except requests.exceptions.ConnectionError as e:
                    # Реально нет интернета или недоступен сервер Telegram (ConnectTimeout)
                    logger.error(f"Нет связи с сервером Telegram (ConnectionError): {e}")
                    break  # Сети нет, прерываем цикл, дошлем в следующий раз

                except requests.exceptions.RequestException as e:
                    # Любая другая непредвиденная ошибка сети
                    logger.error(f"Неизвестный сбой сети при отправке пачки: {e}")
                    break

        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке очереди: {e}")


tg_sender = TelegramSender(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


def send_toast(title: str, body: str):
    logger.info(f"[АЛЕРТ] {title} | {body}")

    # 1. Desktop
    if IS_WINDOWS and 'toast' in globals() and toast:
        try:
            toast(title, body, app_id="Skin Watcher", audio={'silent': False})
        except Exception as e:
            logger.error(f"Ошибка Windows Toast: {e}")
    elif not IS_WINDOWS:
        try:
            subprocess.run(['notify-send', title, body], check=False)
        except Exception as e:
            pass

    # 2. Telegram - теперь просто кладет в БД
    tg_sender.enqueue_message(title, body)
