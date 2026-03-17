# src/alerts_sender.py
from typing import Optional
from config import logger
from settings_manager import load_settings
from repositories.queue_repository import QueueRepository
from infrastructure.notifications import TelegramClient, show_desktop_toast

# Инициализируем настройки
settings = load_settings()
TG_BIZ_TOKEN = settings.get("telegram_biz_token", "")
TG_BIZ_CHAT_ID = settings.get("telegram_biz_chat_id", "")
TG_INFO_TOKEN = settings.get("telegram_info_token", "")
TG_INFO_CHAT_ID = settings.get("telegram_info_chat_id", "")


class AlertDispatcher:
    """Оркестратор, который связывает очередь в БД и HTTP-клиент Telegram."""

    def __init__(self, table_name: str, tg_client: TelegramClient):
        self.repo = QueueRepository(table_name)
        self.tg_client = tg_client

    def enqueue(self, title: str, text: str):
        if not self.tg_client.is_configured():
            return

        formatted_message = self.tg_client.format_message(title, text)
        self.repo.enqueue(formatted_message)

    def process_queue(self):
        if not self.tg_client.is_configured():
            return

        pending = self.repo.get_pending()
        if not pending:
            return

        logger.info(f"[{self.repo.table_name}] Склеиваем {len(pending)} сообщений...")

        batches = []
        current_text = ""
        current_ids = []
        separator = "\n\n➖➖➖➖➖➖\n\n"

        for msg in pending:
            if current_text and (len(current_text) + len(separator) + len(msg.message_text) > TelegramClient.MAX_LEN):
                batches.append((current_text, current_ids))
                current_text = msg.message_text
                current_ids = [msg.id]
            else:
                current_text = current_text + separator + msg.message_text if current_text else msg.message_text
                current_ids.append(msg.id)

        if current_text:
            batches.append((current_text, current_ids))

        for batch_text, batch_ids in batches:
            success = self.tg_client.send_batch(batch_text)
            if success:
                self.repo.delete_batch(batch_ids)
                logger.info(f"Успешно обработана пачка из {len(batch_ids)} сообщений!")
            else:
                break  # Если сеть упала, прекращаем отправку остальных пачек


# Создаем глобальные экземпляры (на Фазе 5 мы от них избавимся, но пока пусть будут для совместимости)
biz_client = TelegramClient(TG_BIZ_TOKEN, TG_BIZ_CHAT_ID)
info_client = TelegramClient(TG_INFO_TOKEN, TG_INFO_CHAT_ID)

tg_biz_sender = AlertDispatcher("alert_queue_biz", biz_client)
tg_info_sender = AlertDispatcher("alert_queue_info", info_client)


def send_biz_alert(title: str, body: str):
    logger.info(f"[БИЗНЕС АЛЕРТ] {title} | {body}")
    show_desktop_toast(title, body)
    tg_biz_sender.enqueue(title, body)


def send_info_alert(title: str, body: str):
    logger.info(f"[ИНФО АЛЕРТ] {title} | {body}")
    tg_info_sender.enqueue(title, body)
