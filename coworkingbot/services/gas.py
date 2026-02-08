from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class GasClient:
    def __init__(self, base_url: str, api_token: str) -> None:
        self._base_url = base_url
        self._api_token = api_token

    async def request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("GAS_WEBAPP_URL is empty (check /etc/default/coworking-bot)")
        if not self._api_token:
            raise RuntimeError("API_TOKEN is empty (check /etc/default/coworking-bot)")

        data = {"token": self._api_token, "action": action, **payload}
        logger.debug("Sending GAS request: action=%s payload=%s", action, payload)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._base_url, json=data, timeout=10) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        try:
                            return json.loads(response_text)
                        except json.JSONDecodeError as exc:
                            logger.error("JSON decode error: %s (text=%s)", exc, response_text)
                            return {
                                "status": "error",
                                "message": f"Ошибка формата ответа: {exc}",
                            }
                    logger.error("HTTP error %s from GAS: %s", response.status, response_text)
                    return {
                        "status": "error",
                        "message": f"Ошибка сервера: {response.status}",
                    }
        except TimeoutError:
            logger.error("Timeout when calling GAS")
            return {"status": "error", "message": "Сервер не отвечает. Попробуйте позже."}
        except Exception as exc:
            logger.error("Network error when calling GAS: %s", exc)
            return {"status": "error", "message": f"Ошибка сети: {exc}"}
