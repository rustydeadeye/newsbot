from __future__ import annotations

import base64
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class XPublisher:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.x_api_base_url.rstrip("/")
        self.client_id = settings.x_client_id
        self.client_secret = settings.x_client_secret
        self.access_token = settings.x_access_token
        self.refresh_token = settings.x_refresh_token
        self.token_url = settings.x_token_url

    def publish(self, text: str) -> dict:
        if not self.access_token:
            logger.warning("X OAuth access token not configured; skipping publish")
            return {"status": "skipped", "reason": "missing_access_token", "text": text}

        response = self._publish_request(text)
        if response.status_code == 401 and self.refresh_token:
            logger.info("X access token expired; attempting refresh")
            self._refresh_access_token()
            response = self._publish_request(text)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error("X API returned HTTP %s when publishing", status_code)
            raise RuntimeError(f"x_api_http_error:{status_code}") from exc
        logger.info("Published tweet successfully")
        payload = response.json()
        return {"status": "posted", **payload}

    def _publish_request(self, text: str) -> httpx.Response:
        try:
            return httpx.post(
                f"{self.base_url}/tweets",
                headers={"Authorization": f"Bearer {self.access_token}"},
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
            response = httpx.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=20.0,
            )
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
