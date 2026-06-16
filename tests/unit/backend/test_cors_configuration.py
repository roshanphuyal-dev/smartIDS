from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import Settings


class CorsConfigurationTest(unittest.TestCase):
    def test_frontend_origins_parse_from_comma_separated_setting(self) -> None:
        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL="redis://127.0.0.1:6379/0",
            SESSION_SECRET="test-secret",
            PASSWORD_RESET_BASE_URL="http://127.0.0.1:3000/reset-password",
            FRONTEND_ORIGINS="http://localhost:3000, http://127.0.0.1:3000",
        )

        self.assertEqual(
            settings.frontend_origins,
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
        )

    def test_cors_allows_configured_frontend_origin_with_credentials(self) -> None:
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        with TestClient(app) as client:
            response = client.get("/health", headers={"Origin": "http://localhost:3000"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
