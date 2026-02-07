import os

import aiohttp
from dotenv import load_dotenv

load_dotenv("/home/coworkingbot/.env")

GAS_WEBAPP_URL = os.getenv("GAS_WEBAPP_URL", "").strip()
API_TOKEN = os.getenv("API_TOKEN", "").strip()


async def call_google_script(payload: dict, timeout: int = 30) -> dict:
    if not GAS_WEBAPP_URL:
        raise RuntimeError("GAS_WEBAPP_URL is empty (.env)")
    if not API_TOKEN:
        raise RuntimeError("API_TOKEN is empty (.env)")

    headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
    t = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(timeout=t) as session:
        async with session.post(GAS_WEBAPP_URL, json=payload, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"GAS HTTP {resp.status}: {text[:500]}")
            try:
                return await resp.json()
            except Exception:
                return {"ok": True, "raw": text}
