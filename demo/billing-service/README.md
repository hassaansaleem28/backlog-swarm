# billing-service

Invoices, tax and totals in the customer's currency, as a small Flask service.

Part of the [Backlog Swarm](https://github.com/hassaansaleem28/backlog-swarm)
demo fleet. Its dependencies are pinned to versions with known
vulnerabilities on purpose; do not deploy it. `.swarm.yml` tells the swarm how
to install and test it and that `migrations/` is off limits.

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest
```
