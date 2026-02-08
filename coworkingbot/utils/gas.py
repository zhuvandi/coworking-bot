import aiohttp

from coworkingbot.config import API_TOKEN, GAS_WEBAPP_URL


async def call_google_script(payload: dict, timeout: int = 30) -> dict:
    if not GAS_WEBAPP_URL:
        raise RuntimeError("GAS_WEBAPP_URL is empty (check /etc/default/coworking-bot)")
    if not API_TOKEN:
        raise RuntimeError("API_TOKEN is empty (check /etc/default/coworking-bot)")

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
