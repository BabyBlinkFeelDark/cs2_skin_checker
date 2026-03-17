# src/repositories/queue_repository.py
from typing import List
from config import logger
from database import get_db_connection
from domain.models import QueuedMessage


class QueueRepository:
    """Управляет очередями сообщений в базе данных."""

    def __init__(self, table_name: str):
        self.table_name = table_name

    def enqueue(self, message: str) -> bool:
        """Кладет сообщение в очередь."""
        try:
            with get_db_connection() as conn:
                conn.execute(
                    f"INSERT INTO {self.table_name} (message_text, status) VALUES (?, ?)",
                    (message, 'pending')
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка записи в очередь {self.table_name}: {e}")
            return False

    def get_pending(self) -> List[QueuedMessage]:
        """Достает все неотправленные сообщения в виде DTO."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT id, message_text FROM {self.table_name} WHERE status = 'pending' ORDER BY id ASC")
                rows = cursor.fetchall()

                return [QueuedMessage(id=row['id'], message_text=row['message_text']) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка чтения очереди {self.table_name}: {e}")
            return []

    def delete_batch(self, message_ids: List[int]):
        """Удаляет пачку успешно отправленных сообщений."""
        if not message_ids:
            return
        try:
            with get_db_connection() as conn:
                placeholders = ','.join('?' * len(message_ids))
                conn.execute(f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})", tuple(message_ids))
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка удаления из {self.table_name}: {e}")

    def get_count(self) -> int:
        """Считает количество зависших сообщений."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE status = 'pending'")
                return cursor.fetchone()[0]
        except Exception:
            return 0
