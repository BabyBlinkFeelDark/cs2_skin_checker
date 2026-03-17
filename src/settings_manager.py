# src/settings_manager.py
import json
from config import logger, LEGACY_SETTINGS_PATH
from database import get_db_connection


def _migrate_json_to_db():
    """Разовая миграция: переносит данные из старого settings.json в базу данных."""
    if not LEGACY_SETTINGS_PATH.exists():
        return

    try:
        with open(LEGACY_SETTINGS_PATH, "r", encoding="utf-8") as f:
            old_settings = json.load(f)

        with get_db_connection() as conn:
            for key, value in old_settings.items():
                # Преобразуем все значения в строки для универсального хранения в БД
                conn.execute("""
                    INSERT INTO app_settings (setting_key, setting_value) 
                    VALUES (?, ?)
                    ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
                """, (key, str(value)))
            conn.commit()

        logger.info(f"Миграция настроек из {LEGACY_SETTINGS_PATH} в БД прошла успешно.")
        # Можно даже удалить файл после миграции:
        # LEGACY_SETTINGS_PATH.unlink()
    except Exception as e:
        logger.error(f"Ошибка при миграции settings.json в БД: {e}")


def load_settings() -> dict:
    """Загружает настройки из БД. Если нужно, делает миграцию из старого JSON."""
    _migrate_json_to_db()

    settings_dict = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT setting_key, setting_value FROM app_settings")
            rows = cursor.fetchall()

            for row in rows:
                key = row['setting_key']
                val = row['setting_value']

                # Конвертируем строки обратно в нужные типы
                if key in ('drop_threshold_percent', 'rise_threshold_percent', 'min_difference_dollars'):
                    settings_dict[key] = float(val) if val else 0.0
                elif key in ('check_interval_hours',):
                    settings_dict[key] = int(val) if val else 1
                else:
                    settings_dict[key] = val  # Строки (steam_id, токены)

        return settings_dict
    except Exception as e:
        logger.error(f"Ошибка чтения настроек из БД: {e}")
        return {}


def update_setting(key: str, value: any):
    """Обновляет одну настройку в БД (пригодится для веб-морды)."""
    try:
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE app_settings 
                SET setting_value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE setting_key = ?
            """, (str(value), key))
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления настройки {key}: {e}")
