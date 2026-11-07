from __future__ import annotations

from threading import Lock


class InvoiceBook:
    """Invoices kept in memory; the real service stores them in Postgres."""

    def __init__(self) -> None:
        self._invoices: dict[int, dict] = {}
        self._lock = Lock()

    def add(self, customer: str, currency: str, lines: list[dict]) -> dict:
        with self._lock:
            invoice_id = len(self._invoices) + 1
            invoice = {
                "id": invoice_id,
                "customer": customer,
                "currency": currency,
                "lines": lines,
            }
            self._invoices[invoice_id] = invoice
            return invoice

    def get(self, invoice_id: int) -> dict | None:
        return self._invoices.get(invoice_id)
