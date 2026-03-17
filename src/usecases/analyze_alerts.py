# src/usecases/analyze_alerts.py
from config import logger
from domain.models import AlertEvent
from repositories.price_repository import PriceRepository
from alerts_sender import send_biz_alert


class AnalyzeAlertsUseCase:
    """Сценарий: Анализ истории цен, расчет процентов и фильтрация спама/фейков."""

    def __init__(
            self,
            price_repo: PriceRepository,
            drop_threshold: float,
            rise_threshold: float,
            min_diff_dollars: float,
            min_healthy_volume: int = 5  # Порог защиты от фейковых пампов
    ):
        self.price_repo = price_repo
        self.drop_threshold = drop_threshold
        self.rise_threshold = rise_threshold
        self.min_diff_dollars = min_diff_dollars
        self.min_healthy_volume = min_healthy_volume

    def execute(self):
        logger.info("Проверка сигналов изменения цены...")

        items = self.price_repo.get_price_windows()
        alerts_found = 0

        for item in items:
            current_price = item['current_price']
            if not current_price:
                continue

            windows = {
                '24ч': item['price_24h'],
                '7дн': item['price_7d'],
                'Точка входа': item['baseline_price']
            }

            trigger_window, trigger_direction, trigger_change = None, None, 0.0

            for window_name, old_price in windows.items():
                if not old_price or old_price <= 0:
                    continue

                if abs(current_price - old_price) < self.min_diff_dollars:
                    continue

                percent_change = ((current_price - old_price) / old_price) * 100

                direction = None
                if percent_change <= -self.drop_threshold:
                    direction = 'drop'
                elif percent_change >= self.rise_threshold:
                    direction = 'rise'

                if direction:
                    trigger_window = window_name
                    trigger_direction = direction
                    trigger_change = percent_change
                    break

            if not trigger_direction:
                continue

            # Анти-спам (Кулдауны)
            event = AlertEvent(item['market_item_id'], trigger_window, trigger_direction)
            if self.price_repo.has_recent_alert(event):
                continue

            self.price_repo.log_alert_event(event)

            # --- ЗАЩИТА ОТ ФЕЙК-ПАМПОВ (Проверка объема) ---
            # Достаем объем продаж для текущей цены из базы
            current_volume = item.get('current_volume', 0)
            volume_warning = ""
            if current_volume < self.min_healthy_volume:
                volume_warning = f"\n⚠️ <b>ОСТОРОЖНО: Низкая ликвидность!</b> За 24ч продано всего {current_volume} шт."

            # Формирование карточки
            net_price = current_price / 1.15
            title_emoji = "📈 ВЗЛЕТ" if trigger_direction == 'rise' else "📉 ПАДЕНИЕ"
            title = f"{title_emoji}: {item['market_hash_name']}"

            msg_lines = [
                f"⚡ Триггер: <b>{trigger_window}</b> ({trigger_change:+.1f}%)",
                f"💰 Текущая цена: <b>${current_price:.2f}</b>{volume_warning}",
                "➖➖➖➖➖➖",
                "📊 <b>Динамика:</b>"
            ]

            for w_name, old_p in windows.items():
                if old_p and old_p > 0:
                    diff_pct = ((current_price - old_p) / old_p) * 100
                    emoji = "🟢" if diff_pct > 0 else "🔴" if diff_pct < 0 else "⚪️"
                    msg_lines.append(f"• За {w_name}: {emoji} {diff_pct:+.1f}% (от ${old_p:.2f})")

            msg_lines.extend([
                "➖➖➖➖➖➖",
                "💵 <b>Доход на баланс:</b>",
                f"С учетом комиссии Steam: ~<b>${net_price:.2f}</b>"
            ])

            send_biz_alert(title, "\n".join(msg_lines))
            alerts_found += 1

        logger.info(f"Проверка завершена. Отправлено сигналов: {alerts_found}")
