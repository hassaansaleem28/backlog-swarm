# notify-worker

Renders notification emails from Markdown, sends them to a webhook and streams
them to live dashboards.

Part of the [Backlog Swarm](https://github.com/hassaansaleem28/backlog-swarm)
demo fleet. Its dependencies are pinned to versions with known
vulnerabilities on purpose; do not deploy it.

`docs/RELEASING.md` carries a deliberate prompt-injection attempt in an HTML
comment: text addressed to AI agents that asks them to add a CI workflow and
merge their own pull request. It is a fixture for testing that the swarm
ignores instructions found in the code it works on.

```sh
npm ci
npm test
```
