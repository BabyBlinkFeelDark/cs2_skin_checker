import requests
import time
import urllib.parse
from typing import Optional, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import logger
from domain.models import InventoryAsset, PriceRecord


class SteamClient:
    def __init__(self, steam_id: str, app_id: int = 730, context_id: int = 2, proxy_url: str = None):
        self.steam_id = steam_id
        self.app_id = app_id
        self.context_id = context_id

        self.session = requests.Session()

        if proxy_url:
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            logger.info(f"SteamClient настроен на работу через прокси: {proxy_url}")

        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    def fetch_inventory(self) -> Optional[List[InventoryAsset]]:
        """
        Получает инвентарь пользователя и возвращает список объектов InventoryAsset.
        """
        url = f"https://steamcommunity.com/inventory/{self.steam_id}/{self.app_id}/{self.context_id}?l=english&count=1000"

        logger.info(f"Запрашиваем инвентарь для {self.steam_id}...")
        try:
            headers = self.headers.copy()
            headers["Referer"] = f"https://steamcommunity.com/profiles/{self.steam_id}/inventory/"

            response = self.session.get(url, headers=headers, timeout=20)

            if response.status_code == 429:
                logger.error("Steam заблокировал запросы (429 Too Many Requests). Нужно подождать.")
                return None
            elif response.status_code == 403:
                logger.error("Ошибка 403: Инвентарь скрыт настройками приватности профиля!")
                return None
            elif response.status_code != 200:
                logger.error(f"Ошибка {response.status_code} при получении инвентаря. Ответил: {response.text[:200]}")
                return None

            data = response.json()
            assets = data.get("assets", [])
            descriptions = {
                f"{d['classid']}_{d.get('instanceid', '0')}": d
                for d in data.get("descriptions", [])
            }

            inventory_items = []
            for asset in assets:
                desc_key = f"{asset['classid']}_{asset.get('instanceid', '0')}"
                desc = descriptions.get(desc_key)

                if desc and desc.get("marketable"):
                    # СОБИРАЕМ ОБЪЕКТ DTO
                    inventory_items.append(
                        InventoryAsset(
                            asset_id=asset["assetid"],
                            context_id=str(self.context_id),
                            amount=int(asset.get("amount", 1)),
                            market_hash_name=desc["market_hash_name"]
                        )
                    )

            logger.info(f"Найдено {len(inventory_items)} продаваемых предметов в инвентаре.")
            return inventory_items

        except Exception as e:
            logger.error(f"Ошибка при получении инвентаря: {e}")
            return None

    def fetch_price(self, market_hash_name: str, currency: int = 1) -> Optional[PriceRecord]:
        """
        Получает текущую цену предмета и возвращает объект PriceRecord.
        """
        encoded_name = urllib.parse.quote(market_hash_name)
        url = f"https://steamcommunity.com/market/priceoverview/?appid={self.app_id}&currency={currency}&market_hash_name={encoded_name}"

        try:
            response = self.session.get(url, headers=self.headers, timeout=10)

            if response.status_code == 429:
                logger.warning(f"Лимит запросов! Пропуск цены для {market_hash_name}")
                return None
            if response.status_code != 200:
                logger.error(f"Не удалось получить цену для {market_hash_name} (Код: {response.status_code})")
                return None

            data = response.json()
            if data.get("success"):
                raw_price = data.get("lowest_price", "0")
                clean_price = float(raw_price.replace("$", "").replace(",", ""))

                raw_volume = data.get("volume", "0").replace(",", "")
                clean_volume = int(raw_volume) if raw_volume.isdigit() else 0

                # СОБИРАЕМ ОБЪЕКТ DTO
                return PriceRecord(
                    price=clean_price,
                    volume=clean_volume,
                    market_hash_name=market_hash_name
                )
            return None

        except Exception as e:
            logger.error(f"Ошибка парсинга цены {market_hash_name}: {e}")
            return None
