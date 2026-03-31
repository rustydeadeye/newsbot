from __future__ import annotations

import base64
import logging
from typing import Callable

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class XPublisher:
    def __init__(
        self,
        token_store: dict | None = None,
        on_token_refresh: Callable[[str, str], None] | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = settings.x_api_base_url.rstrip("/")
        self.client_id = settings.x_client_id
        self.client_secret = settings.x_client_secret
        self.token_url = settings.x_token_url
        self._on_token_refresh = on_token_refresh

        # Prefer live token_store (DB) over settings (.env)
        store = token_store or {}
        self.access_token = store.get("x_access_token") or settings.x_access_token
        self.refresh_token = store.get("x_refresh_token") or settings.x_refresh_token

    def publish(self, text: str, idempotency_key: str | None = None) -> dict:
        if not self.access_token:
            logger.warning("X OAuth access token not configured; skipping publish")
            return {"status": "skipped", "reason": "missing_access_token", "text": text}

        response = self._publish_request(text, idempotency_key)

        if response.status_code == 429:
            retry_after = int(response.headers.get("retry-after", "900"))
            logger.warning("X API rate limited; retry_after=%ds", retry_after)
            return {"status": "rate_limited", "retry_after_seconds": retry_after}

        if response.status_code == 401 and self.refresh_token:
            logger.info("X access token expired; attempting refresh")
            self._refresh_access_token()
            response = self._publish_request(text, idempotency_key)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error("X API returned HTTP %s when publishing", status_code)
            raise RuntimeError(f"x_api_http_error:{status_code}") from exc

        logger.info("Published tweet successfully")
        payload = response.json()
        return {"status": "posted", **payload}

    def fetch_tweet_metrics(self, tweet_id: str) -> dict | None:
        if not self.access_token:
            return None
        try:
            response = httpx.get(
                f"{self.base_url}/tweets/{tweet_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"tweet.fields": "public_metrics"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            return data.get("public_metrics")
        except Exception:
            logger.warning("Failed to fetch metrics for tweet_id=%s", tweet_id, exc_info=True)
            return None

    def _publish_request(self, text: str, idempotency_key: str | None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            return httpx.post(
                f"{self.base_url}/tweets",
                headers=headers,
                json={"text": text},
                timeout=20.0,
            )
        except httpx.RequestError as exc:
            logger.error("X API request failed (%s)", type(exc).__name__)
            raise RuntimeError(f"x_api_request_error:{type(exc).__name__}") from exc

    def _refresh_access_token(self) -> None:
        if not self.refresh_token or not self.client_id:
            raise RuntimeError("x_oauth_refresh_not_configured")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.client_secret:
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {basic}"

        try:
            response = httpx.post(self.token_url, headers=headers, data=data, timeout=20.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error("X token refresh returned HTTP %s", status_code)
            raise RuntimeError(f"x_oauth_refresh_http_error:{status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("X token refresh request failed (%s)", type(exc).__name__)
            raise RuntimeError(f"x_oauth_refresh_request_error:{type(exc).__name__}") from exc

        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError("x_oauth_refresh_missing_access_token")

        self.access_token = access_token
        self.refresh_token = payload.get("refresh_token", self.refresh_token)

        # Persist new tokens back to DB via callback
        if self._on_token_refresh:
            try:
                self._on_token_refresh(self.access_token, self.refresh_token)
            except Exception:
                logger.warning("Failed to persist refreshed tokens", exc_info=True)
