from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class MarketItem:
    """Описывает уникальный тип предмета на Торговой площадке."""
    app_id: int
    market_hash_name: str
    id: Optional[int] = None  # ID в нашей базе (появляется после сохранения)
    is_marketable: bool = True

@dataclass
class InventoryAsset:
    """Описывает конкретный экземпляр предмета в инвентаре пользователя."""
    asset_id: str
    context_id: str
    amount: int
    market_hash_name: str  # Удобно хранить при парсинге из Steam
    market_item_id: Optional[int] = None # ID связи с MarketItem в БД
    baseline_price: Optional[float] = None
    last_seen_at: Optional[datetime] = None

@dataclass
class PriceRecord:
    """Описывает исторический срез цены предмета."""
    price: float
    volume: int
    market_hash_name: str = "" # Для удобства проброса из API
    market_item_id: Optional[int] = None
    recorded_at: Optional[datetime] = None

@dataclass
class AlertEvent:
    """Описывает событие срабатывания алерта (для истории и кулдаунов)."""
    market_item_id: int
    window: str
    direction: str
    triggered_at: Optional[datetime] = None

@dataclass
class QueuedMessage:
    """Описывает сообщение, ожидающее отправки в Telegram."""
    message_text: str
    status: str = 'pending'
    id: Optional[int] = None
    created_at: Optional[datetime] = None
