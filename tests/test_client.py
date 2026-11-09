import pytest
import requests

from brevo_warehouse.client import BrevoClient, BrevoError
from conftest import fixture


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession(requests.Session):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):  # noqa: D401
        self.calls.append(params)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make(responses):
    s = FakeSession(responses)
    return BrevoClient("test-key", session=s, backoff=0), s


def test_missing_key_is_refused():
    with pytest.raises(BrevoError):
        BrevoClient("")


def test_pagination_reads_every_page():
    client, s = make([FakeResponse(200, fixture("campaigns_page1.json")),
                      FakeResponse(200, fixture("campaigns_page2.json"))])
    ids = [c["id"] for c in client.iter_email_campaigns(page_size=2)]
    assert ids == [901, 902, 903]
    assert [c["offset"] for c in s.calls] == [0, 2]


def test_retries_then_succeeds():
    client, s = make([FakeResponse(503), FakeResponse(200, {"campaigns": [], "count": 0})])
    assert list(client.iter_email_campaigns()) == []
    assert len(s.calls) == 2


def test_gives_up_instead_of_returning_partial_data():
    client, _ = make([FakeResponse(503)] * 3)
    with pytest.raises(BrevoError):
        list(client.iter_email_campaigns())


def test_client_error_is_not_retried():
    client, s = make([FakeResponse(401, {"message": "unauthorized"})])
    with pytest.raises(BrevoError):
        client.get("/account")
    assert len(s.calls) == 1


def test_proxy_detection_is_disabled():
    client, s = make([])
    assert s.trust_env is False
