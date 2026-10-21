import unittest

import httpx
from fastapi import HTTPException

from src.mcp_server.dummy_api_client_service import AsyncERPNextService


class ERPNextSessionAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_uses_user_sid_cookie(self):
        observed_cookies = []
        async_client_class = httpx.AsyncClient

        def handler(request: httpx.Request) -> httpx.Response:
            observed_cookies.append(request.headers.get("cookie"))
            return httpx.Response(200, json={"data": {"name": "MAT-MR-2026-00006"}})

        transport = httpx.MockTransport(handler)

        def make_client(**kwargs):
            return async_client_class(transport=transport, **kwargs)

        original_async_client = httpx.AsyncClient
        httpx.AsyncClient = make_client
        try:
            service = AsyncERPNextService("https://erpnext.example")
            result = await service.request(
                "GET",
                "api/resource/Material Request/MAT-MR-2026-00006",
                erpnext_sid="user-session",
            )
        finally:
            httpx.AsyncClient = original_async_client

        self.assertEqual(result["data"]["name"], "MAT-MR-2026-00006")
        self.assertEqual(observed_cookies, ["sid=user-session"])

    async def test_request_rejects_missing_user_session(self):
        service = AsyncERPNextService("https://erpnext.example")

        with self.assertRaises(HTTPException) as error:
            await service.request("GET", "api/resource/Material Request/MR-1")

        self.assertEqual(error.exception.status_code, 401)
