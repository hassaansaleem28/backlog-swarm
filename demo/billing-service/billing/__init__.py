"""Billing service: invoices, tax and totals in the customer's currency."""

from __future__ import annotations

import requests
import yaml
from flask import Flask, abort, current_app, jsonify, request

from .invoices import InvoiceBook


def create_app(config_path: str = "config.yml") -> Flask:
    app = Flask(__name__)
    app.config["BILLING_CONFIG_PATH"] = config_path
    app.config["BILLING"] = {}
    book = InvoiceBook()

    @app.before_first_request
    def load_billing_config():
        with open(current_app.config["BILLING_CONFIG_PATH"]) as f:
            current_app.config["BILLING"] = yaml.load(f)

    @app.post("/invoices")
    def create_invoice():
        body = request.get_json(force=True)
        if not body.get("customer") or not body.get("lines"):
            abort(400, "customer and lines are required")
        invoice = book.add(body["customer"], body.get("currency", "USD"), body["lines"])
        return jsonify(invoice), 201

    @app.get("/invoices/<int:invoice_id>/total")
    def invoice_total(invoice_id: int):
        invoice = book.get(invoice_id)
        if invoice is None:
            abort(404)
        settings = current_app.config["BILLING"]
        subtotal = sum(line["price"] * line["qty"] for line in invoice["lines"])
        taxed = subtotal * (1 + settings["tax_rate"])
        rate = 1.0
        if invoice["currency"] != settings["base_currency"]:
            response = requests.get(
                settings["rates_url"],
                params={"base": settings["base_currency"]},
                timeout=5,
            )
            response.raise_for_status()
            rate = response.json()["rates"][invoice["currency"]]
        return jsonify(
            {"currency": invoice["currency"], "total": round(taxed * rate, 2)}
        )

    return app
