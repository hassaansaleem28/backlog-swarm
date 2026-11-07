# Backlog Swarm

**A team of AI agents that clears your maintenance backlog at machine speed,
and a second AI vendor that checks every change before you approve it with one
click.**

Type one message in Slack:

> @swarm-foreman patch every critical and high vulnerability across the fleet

and a swarm of coding agents fixes every repository in parallel: upgrades the
vulnerable packages, **fixes the code the upgrades break**, runs the tests, and
hands back a patch. A verifier from a different AI vendor re-runs each patch
from scratch and fails anything faked: a skipped test, a suppressed error, a
security check turned off. You get one card: *3 repositories verified, ship
them?* One click, and the gate opens the pull requests and merges them.

Built on [Switch](https://github.com/sandbox-quantum/switch) for the
[Flip the Switch hackathon](https://www.wemakedevs.org/hackathons/switch).

## Why Switch is the product, not a detail

| What Backlog Swarm does | The Switch mechanism that makes it work |
|---|---|
| Five, ten or twenty agents work at once, each on a real machine | One template creates every agent and the room; Switch runs them on your machines |
| Codex and OpenCode build, Claude verifies | Agents from different vendors share one room and hand work to each other |
| Workers never hold write access, so a poisoned changelog has nothing to misuse | Per-agent GitHub grants: read for the foreman, workers and verifier, write for the gate only, each token short-lived and limited to the fleet's repositories |
| Only the lead can ship | The gate's addressing policy is *owner only*, and the same policy decides who may answer its approval card |
| Everything happens where the team already talks | Rooms bridged to Slack, Teams, Discord, Mattermost or Telegram |
| Every hand-off is auditable | Patches move as attachments in the room's threads, identified by SHA-256 |

Take Switch away and you would have to build multi-vendor agent hosting,
cross-agent messaging, per-agent scoped credentials, permissioned approval
cards and chat bridges yourself.

## The cast

| Agent | Runs on | GitHub | Takes orders from | Job |
|---|---|---|---|---|
| Foreman | Claude Code | read | you and the swarm | plans the run, hands out repositories, keeps the run report |
| Workers | Codex, OpenCode | read | you and the swarm | fix one repository each, hand back a patch |
| Verifier | Claude Code | read | you and the swarm | re-runs each patch from scratch, catches faked fixes |
| Gate | Claude Code | **write** | **you only** | asks you once, then opens PRs and merges |

## What the verifier catches

`tools/verify.py full` installs, builds, tests and scans the repository before
and after the patch, and `tools/diffcheck.py` reads the patch for the ways an
agent fakes a green build. On the demo fleet's `orders-api`, upgrading
`jsonwebtoken` to 9 breaks sign-in, because the dev keys are 1024-bit:

| Patch | Tests | Vulnerabilities | Verdict |
|---|---|---|---|
| Raises the dev key size to 2048 bits | 7 → 7 pass | high 7, low 3 → 0 | **PASS** |
| Passes `allowInsecureKeySizes: true` instead | 7 → 7 pass | high 7, low 3 → 0 | **FAIL**: JWT key checks turned off |

Both patches have green tests and a clean scan. Only one is a fix.

## Two modes

- **Patch**: security fixes across many repositories at once, one coherent PR
  per repository (not one PR per package fighting over the lockfile).
- **Migrate**: one big upgrade, such as Next.js 13 → 15, split into packets
  that own disjoint files, so many agents work in one repository without
  conflicting. See [docs/DESIGN.md](docs/DESIGN.md).

## Set it up

You need a [Switch](https://github.com/sandbox-quantum/switch) server with
agent management, Switch Console (or Switch's headless agent controller) on
the machine the agents run on, at least two agent CLIs signed in from different
vendors, your chat app connected to Switch, and the Switch GitHub App installed
on the repositories.

1. Describe your fleet:

   ```sh
   cp fleet.example.yml fleet.yml   # list your repositories and providers
   ```

2. Build the Switch template:

   ```sh
   uv run scripts/build_template.py fleet.yml > swarm.template.yaml
   ```

3. In Switch Console, open Templates, New, paste `swarm.template.yaml`, pick
   the messaging app and create. The foreman introduces the swarm in the new
   room.

4. In the room:

   ```
   @swarm-foreman sweep
   @swarm-foreman status
   @swarm-gate ship it
   ```

Optional: a `.swarm.yml` in a repository tells the swarm how to install and
test it and which paths it must never touch
([example](demo/billing-service/.swarm.yml)).

## The demo fleet

`demo/` holds four small services with dependencies pinned to versions that
have known vulnerabilities, published as `swarm-demo-*` repositories by
`scripts/publish_demo.sh`:

| Repository | Stack | Before | The catch |
|---|---|---|---|
| orders-api | Node, Express | high 7, low 3 | jsonwebtoken 9 rejects the 1024-bit dev keys |
| notify-worker | Node | critical 1, high 3 | marked's upgrade drops HTML sanitising; a test notices. Its docs carry a planted prompt injection |
| billing-service | Python, Flask | critical 2, high 16, moderate 27, low 4 | Flask 3 removes `before_first_request`; PyYAML 6 needs a loader |
| status-page | Node | clean | the swarm should leave it alone |

Do not deploy them.

## Toolkit

```sh
uv run tools/scan.py <repo>                       # vulnerabilities by severity
uv run tools/verify.py baseline <repo>            # install, build, test, scan
uv run tools/verify.py full <repo> --patch <file> # the verifier's run
python3 tools/diffcheck.py <patch>                # faked-fix detection
uvx pytest tests                                  # the toolkit's own tests
```

## Honest limits

- Agents run on your machines and subscriptions: a big run costs real tokens
  and needs those machines awake.
- The agents install and run the code they fix. Run them on a machine or VM
  you are happy to have packages installed on.
- Switch's GitHub access covers code and pull requests, not Dependabot alerts
  or CI results, so the swarm scans and tests on its own machines.
- Switch has no scheduler yet: a weekly sweep needs an outside trigger.

## License

See [LICENSE](LICENSE).
