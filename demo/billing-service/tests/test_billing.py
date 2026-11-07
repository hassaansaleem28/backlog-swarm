import pytest
import requests
import yaml

from billing import create_app


class FakeRates:
    def __init__(self):
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self

    def raise_for_status(self):
        pass

    def json(self):
        return {"base": "USD", "rates": {"EUR": 0.5}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    config = tmp_path / "config.yml"
    config.write_text(
        "base_currency: USD\ntax_rate: 0.1\nrates_url: https://rates.test/rates\n"
    )
    rates = FakeRates()
    monkeypatch.setattr(requests, "get", rates)
    app = create_app(str(config))
    app.testing = True
    client = app.test_client()
    client.rates = rates
    return client


def test_creates_an_invoice(client):
    response = client.post(
        "/invoices",
        json={"customer": "acme", "lines": [{"price": 10, "qty": 2}]},
    )
    assert response.status_code == 201
    assert response.get_json()["id"] == 1


def test_rejects_an_invoice_without_lines(client):
    assert client.post("/invoices", json={"customer": "acme"}).status_code == 400


def test_totals_with_tax_in_the_base_currency(client):
    client.post("/invoices", json={"customer": "acme", "lines": [{"price": 10, "qty": 2}]})
    response = client.get("/invoices/1/total")
    assert response.get_json() == {"currency": "USD", "total": 22.0}
    assert client.rates.calls == []


def test_converts_to_the_invoice_currency(client):
    client.post(
        "/invoices",
        json={"customer": "acme", "currency": "EUR", "lines": [{"price": 10, "qty": 2}]},
    )
    response = client.get("/invoices/1/total")
    assert response.get_json() == {"currency": "EUR", "total": 11.0}
    assert client.rates.calls == [("https://rates.test/rates", {"base": "USD"})]


def test_unknown_invoice_is_404(client):
    assert client.get("/invoices/99/total").status_code == 404


def test_config_cannot_construct_python_objects(tmp_path, monkeypatch):
    config = tmp_path / "config.yml"
    config.write_text(
        "base_currency: USD\ntax_rate: 0.1\n"
        "rates_url: !!python/object/apply:os.getcwd []\n"
    )
    monkeypatch.setattr(requests, "get", FakeRates())
    with pytest.raises(yaml.YAMLError):
        app = create_app(str(config))
        app.testing = True
        client = app.test_client()
        client.post("/invoices", json={"customer": "acme", "lines": [{"price": 1, "qty": 1}]})
        client.get("/invoices/1/total")
