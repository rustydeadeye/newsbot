from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class XPublisher:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.x_api_base_url.rstrip("/")
        self.bearer_token = settings.x_bearer_token

    def publish(self, text: str) -> dict:
        if not self.bearer_token:
            logger.warning("X bearer token not configured; skipping publish")
            return {"status": "skipped", "reason": "missing_token", "text": text}
        try:
            response = httpx.post(
                f"{self.base_url}/tweets",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                json={"text": text},
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error("X API returned HTTP %s when publishing", status_code)
            raise RuntimeError(f"x_api_http_error:{status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("X API request failed (%s)", type(exc).__name__)
            raise RuntimeError(f"x_api_request_error:{type(exc).__name__}") from exc
        logger.info("Published tweet successfully")
        payload = response.json()
        return {"status": "posted", **payload}
