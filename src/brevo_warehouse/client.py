"""A small, read-only Brevo API client with retries and pagination."""
from __future__ import annotations

import time
from typing import Any, Iterator

import requests

RETRY_STATUSES = {429, 500, 502, 503, 504}


def use_system_certificates() -> bool:
    """Trust the operating system's certificate store when the `truststore` package is installed.

    On a corporate network, HTTPS traffic is often re-signed by the company's own
    certificate authority. Windows already trusts it; Python does not. `truststore`
    makes Python use the Windows store, so no certificate file has to be maintained.
    """
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


class BrevoError(RuntimeError):
    """Raised when the Brevo API cannot be reached or answers with an error."""


class BrevoClient:
    def __init__(self, api_key: str, base_url: str = "https://api.brevo.com/v3",
                 verify_ssl: bool | str = True, timeout: int = 60,
                 session: requests.Session | None = None, max_retries: int = 3,
                 backoff: float = 1.0) -> None:
        if not api_key:
            raise BrevoError("BREVO_API_KEY is missing: copy .env.example to .env and fill it in.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.session = session or requests.Session()
        # Corporate proxies are detected automatically on some Windows machines and break calls.
        self.session.trust_env = False
        if verify_ssl is not False and use_system_certificates():
            verify_ssl = True  # the system store replaces any certificate file
        self.session.verify = verify_ssl
        self.session.headers.update({"api-key": api_key, "accept": "application/json"})

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
            else:
                if resp.status_code in RETRY_STATUSES:
                    last_error = BrevoError(f"HTTP {resp.status_code} on {path}")
                elif resp.status_code >= 400:
                    raise BrevoError(f"HTTP {resp.status_code} on {path}: {resp.text[:200]}")
                else:
                    return resp.json()
            if attempt < self.max_retries - 1:
                time.sleep(self.backoff * (2 ** attempt))
        raise BrevoError(f"Brevo API unreachable after {self.max_retries} attempts: {last_error}")

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with the same error handling as get(). Used only to send the owner's alert email."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise BrevoError(f"Brevo API unreachable on {path}: {exc}") from exc
        if resp.status_code >= 400:
            raise BrevoError(f"HTTP {resp.status_code} on {path}: {resp.text[:200]}")
        return resp.json() if resp.content else {}

    def iter_email_campaigns(self, status: str = "sent", page_size: int = 100,
                             statistics: str = "globalStats") -> Iterator[dict[str, Any]]:
        """Yield every email campaign with its global statistics, page by page.

        Stops on an empty page; raises BrevoError instead of returning partial data.
        """
        offset = 0
        total = None
        while True:
            payload = self.get("/emailCampaigns", params={
                "status": status, "limit": page_size, "offset": offset,
                "statistics": statistics, "sort": "desc",
            })
            batch = payload.get("campaigns") or []
            total = payload.get("count", total)
            if not batch:
                return
            yield from batch
            offset += len(batch)
            if total is not None and offset >= total:
                return

    def iter_contact_lists(self, page_size: int = 50) -> Iterator[dict[str, Any]]:
        """Yield every contact list with its subscriber counts, page by page (max 50 per page)."""
        offset = 0
        total = None
        while True:
            payload = self.get("/contacts/lists", params={
                "limit": page_size, "offset": offset, "sort": "desc",
            })
            batch = payload.get("lists") or []
            total = payload.get("count", total)
            if not batch:
                return
            yield from batch
            offset += len(batch)
            if total is not None and offset >= total:
                return
