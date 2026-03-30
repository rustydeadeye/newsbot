from types import SimpleNamespace

import httpx

from app.services.publishing.x_client import XPublisher


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self) -> dict:
        return self._payload


def test_publish_refreshes_access_token_on_401(monkeypatch) -> None:
    publisher = XPublisher()
    publisher.base_url = "https://api.x.com/2"
    publisher.token_url = "https://api.x.com/2/oauth2/token"
    publisher.client_id = "client-id"
    publisher.client_secret = None
    publisher.access_token = "expired-token"
    publisher.refresh_token = "refresh-token"

    calls: list[tuple[str, dict | None, dict | None]] = []

    def fake_post(url: str, headers=None, json=None, data=None, timeout=None):
        calls.append((url, json, data))
        if url.endswith("/tweets") and headers["Authorization"] == "Bearer expired-token":
            return _Response(401, {"title": "Unauthorized"})
        if url.endswith("/oauth2/token"):
            return _Response(200, {"access_token": "fresh-token", "refresh_token": "fresh-refresh"})
        if url.endswith("/tweets") and headers["Authorization"] == "Bearer fresh-token":
            return _Response(200, {"data": {"id": "123"}})
        raise AssertionError(f"unexpected call: {url}")

    monkeypatch.setattr("app.services.publishing.x_client.httpx.post", fake_post)

    result = publisher.publish("hello world")

    assert result["status"] == "posted"
    assert result["data"]["id"] == "123"
    assert publisher.access_token == "fresh-token"
    assert publisher.refresh_token == "fresh-refresh"
