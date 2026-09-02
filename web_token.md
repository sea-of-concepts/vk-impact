async def get_web_access_token(
        self, remixsid: str | None = None, cookie_p: str | None = None
    ) -> str:
        """Получение временного access_token через login.vk.com по сессионным куки."""
        sid = (remixsid or settings.remixsid or "").strip()
        p = (cookie_p or settings.cookie_p or "").strip()
        user_agent = settings.vk_user_agent
        app_id = settings.vk_web_app_id

        if not sid:
            raise RuntimeError("REMIXSID не настроен в файле конфигурации .env")

        url = "https://login.vk.com/?act=web_token"
        headers = {
            "User-Agent": user_agent,
            "Origin": "https://vk.com",
            "Referer": "https://vk.com/",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
        }
        cookies = {"remixsid": sid}
        if p:
            cookies["p"] = p

        payload = {
            "version": "1",
            "app_id": app_id,
        }

        async with httpx.AsyncClient(http2=True, timeout=15.0) as client:
            response = await client.post(url, headers=headers, cookies=cookies, data=payload)
            response.raise_for_status()
            json_data = response.json()

            if json_data.get("type") == "error":
                error_info = json_data.get("error_info", "Неизвестная ошибка")
                raise RuntimeError(f"Ошибка авторизации login.vk.com: {error_info}")

            token = json_data.get("data", {}).get("access_token")
            if not token:
                raise ValueError(f"Токен не найден в ответе сервера: {json_data}")

            return token