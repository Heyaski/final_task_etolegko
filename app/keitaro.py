from __future__ import annotations

import httpx


class KeitaroError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, json: dict | list | None = None, params: dict | None = None):
        url = f"{self.base_url}/admin_api/v1{path}"
        headers = {"Api-Key": self.api_key, "Accept": "application/json"}
        try:
            response = httpx.request(method, url, headers=headers, json=json, params=params, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise KeitaroError(0, f"Keitaro недоступен: {exc}") from exc
        if response.status_code >= 400:
            message = _error_message(response)
            raise KeitaroError(response.status_code, message)
        if not response.content:
            return {}
        return response.json()

    def list_campaigns(self) -> list:
        return _as_list(self._request("GET", "/campaigns"))

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, data: dict) -> dict:
        return self._request("POST", "/campaigns", json=data)

    def delete_campaign(self, campaign_id: int) -> dict:
        return self._request("DELETE", f"/campaigns/{campaign_id}")

    def list_streams(self, campaign_id: int) -> list:
        return _as_list(self._request("GET", f"/campaigns/{campaign_id}/streams"))

    def create_stream(self, data: dict) -> dict:
        return self._request("POST", "/streams", json=data)

    def update_stream(self, stream_id: int, data: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", json=data)

    def list_offers(self) -> list:
        return _as_list(self._request("GET", "/offers"))

    def get_offer(self, offer_id: int) -> dict:
        return self._request("GET", f"/offers/{offer_id}")

    def list_domains(self) -> list:
        return _as_list(self._request("GET", "/domains"))

    def list_groups(self, group_type: str) -> list:
        return _as_list(self._request("GET", "/groups", params={"type": group_type}))

    def list_traffic_sources(self) -> list:
        return _as_list(self._request("GET", "/traffic_sources"))

    def build_report(self, data: dict) -> dict:
        result = self._request("POST", "/report/build", json=data)
        return result if isinstance(result, dict) else {"rows": result}


def _as_list(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        text = response.text.strip()
        return text or f"Keitaro ответил {response.status_code}"
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            if body.get(key):
                return str(body[key])
        return str(body)
    return str(body)
