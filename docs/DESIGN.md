# Backlog Swarm: design

Backlog Swarm clears software maintenance work at machine speed: security
patches across many repositories at once, and large framework upgrades inside
one repository. It is built on [Switch](https://github.com/sandbox-quantum/switch):
a team of AI agents from different vendors works in a chat room the team
already uses (Slack, Teams, Discord, Mattermost, Telegram), a second vendor's
agent re-checks every change by running it, and one person approves the
result with a single card.

## The cast

| Agent | Typical provider | GitHub access | Who can give it orders | Job |
|---|---|---|---|---|
| `foreman` | Claude Code | Read | The lead (owner), and the swarm's own agents | Plans the run, splits the work, hands it out, integrates the pieces, keeps the run report |
| `worker-1` … `worker-N` | Codex, OpenCode (mixed) | Read | The lead and the swarm's own agents | Takes one piece of work, does it locally, hands back a patch |
| `verifier` | A different vendor from the workers | Read | The lead and the swarm's own agents | Applies each patch to a clean clone, builds, tests, re-scans, and looks for faked fixes |
| `gate` | Claude Code (native question cards) | **Write** | **The lead only** | Asks the lead to approve, then pushes branches, opens PRs and merges |

Only the gate can write to GitHub, and only the lead can command the gate.
Workers read untrusted content all day (dependency changelogs, upgrade guides,
the repository itself), so they never hold a credential that can change
anything. If one is talked into something by a poisoned changelog, it has
nothing to do it with, and it cannot wake the gate.

Work moves between agents as **patch files posted in the room** (Switch
attachments), not as pushes. Every hand-off is visible in the room, and the
patch the verifier tested is byte-for-byte the patch the gate ships.

## Mode 1: Patch (many repositories at once)

The lead types in the channel:

> @foreman patch every critical and high vulnerability across the fleet

1. The foreman reads the fleet list (a room document) and gives each worker a
   repository, one thread per repository.
2. Each worker clones its repository, scans it (`npm audit`, `pip-audit`),
   upgrades the vulnerable packages, **fixes whatever code the upgrade breaks**,
   runs the tests, and posts a patch with a before/after vulnerability count.
3. The verifier applies the patch to a fresh clone, re-runs install, build,
   tests and the scan itself, and checks the diff for cheating (below). It posts
   PASS or FAIL with the reason.
4. A FAIL goes back to the same worker with the verifier's evidence, once. A
   second FAIL is reported as "needs a human", not retried forever.
5. The foreman posts the run report: per repository, vulnerabilities before
   and after, tests, verdict.
6. The lead types `@gate ship it`. The gate posts one card listing the verified
   repositories. The lead approves, and the gate pushes a branch, opens a PR
   per repository, and merges if the lead chose "open and merge".

All bumps for one repository go into **one** PR with one lockfile
regeneration. Dependabot opens one PR per package, and each one conflicts on the
lockfile as soon as the first merges. That is the conflict this mode avoids.

## Mode 2: Migrate (one big upgrade, many agents inside one repository)

The lead types:

> @foreman upgrade apps/web from Next.js 13 to 15

A big upgrade cannot be one agent's one prompt. The diff is too large, the
breakages interact, and a single agent that writes, runs and judges its own work
tends to declare victory early. The swarm works like a migration team.

**1. Stepping stones.** The foreman never jumps several majors at once. 13 → 15
is run as 13 → 14, then 14 → 15, each its own verified PR, because each major
has its own upgrade guide and codemods.

**2. Deterministic first.** The foreman bumps the packages, runs the
framework's official codemods (`npx @next/codemod upgrade` for Next.js), and
regenerates the lockfile. These shared files (`package.json`, the lockfile,
`next.config.*`, shared types) belong to the foreman alone from then on.

**3. Measure the damage.** It runs the build, the type check and the tests and
collects every error, then groups the errors into **packets**, each a set of
files that fail for related reasons (for example: every route that now has to
`await cookies()`).

**4. Packets own files, so workers cannot conflict.** Every file in the
repository belongs to at most one packet. A worker may change only the files its
packet lists; the verifier rejects a patch that touches anything else. Because
no two workers touch the same file, their patches never conflict as text. When
a worker finds it needs a shared file changed, it asks the foreman instead of
editing it, and the foreman changes it on the upgrade branch for everyone.

**5. Integrate continuously.** The foreman applies verified packets one at a
time and re-runs the build after each. Two packets that are fine alone but
break together (a semantic conflict) show up immediately, and the foreman sends
the failing packet back with the error.

**6. Keep up with main.** Teams keep merging while a migration runs. At each
phase boundary the foreman merges `main` into the upgrade branch. Conflicts it
can resolve mechanically it resolves; anything else goes to the lead as a card
with both sides shown.

**7. Phase gates, not per-file approvals.** The lead approves the plan, then
each phase (dependencies and codemods done, all packets green, final
verification), never individual files.

**8. Stop honestly.** When the swarm cannot get a phase green within its budget,
it stops and reports what is left: the failing packets, the errors, what it
tried. A partial migration with an honest checklist is useful. A green build
with skipped tests is not.

## What the verifier checks

It never takes a worker's word for a result. On a clean clone it:

- applies the patch, installs, builds, type-checks, runs the tests and the scan
  itself;
- compares test counts before and after (tests deleted or skipped = FAIL);
- searches the diff for escape hatches: `@ts-ignore`, `@ts-expect-error`,
  `eslint-disable`, new `any`, `.skip`/`xit`, loosened config, lowered coverage
  thresholds;
- checks that only the files the packet owns changed;
- for Patch mode, checks that the scan's count actually dropped.

The verifier comes from a different vendor than the workers on purpose. In a
July 2026 study, Claude reviewing Codex's code raised the pass rate from 71.6%
to 89.7% ([arXiv 2607.21656](https://arxiv.org/abs/2607.21656)), and same-agent
self-checks are where 2026 migration swarms faked their test reports. The run
report keeps a per-vendor record of who caught what, because that balance shifts
with every model release.

## Per-repository settings: `.swarm.yml`

Optional, in the root of a target repository. Without it the agents work out
the commands themselves and say so in the report.

```yaml
install: npm ci
build: npm run build
test: npm test
scan: npm audit --json
protected:            # never changed by the swarm
  - db/migrations/**
  - .github/**
policy:
  max_major_jump: 1   # stepping stones
  open_prs: true
  auto_merge: false   # the lead still approves
```

## How a team adopts it

Nothing is installed into a team's repositories or CI. A team needs:

1. **A Switch server.** Self-hosted (Docker Compose), the local server Switch
   Console sets up, or a server someone already runs for the team.
2. **A machine for the agents.** Switch Console on a workstation, or Switch's
   headless agent controller on a VM so the swarm keeps working when laptops
   close. At least two agent CLIs signed in, from different vendors.
3. **Their chat app connected** to Switch, and **the Switch GitHub App**
   installed on their organisation with the repositories they choose.
4. **The Backlog Swarm template**, imported once in Switch Console's Templates
   page. Its form asks for the repositories, the providers, the lead and the
   channel, and creates the room and all the agents in one click.

From then on the swarm is a chat command away. To share it more widely, the
template can be saved as a shared template on a team's Switch server, and
proposed upstream as an official Switch template so it appears for every Switch
user.

## Honest limits

- Agents run on the team's own machines and subscriptions, so a big run costs
  real tokens and needs those machines awake.
- Switch's GitHub access covers code and pull requests, not Dependabot alerts
  or CI results, so the agents scan and test on their own machines.
- Switch has no scheduler yet, so "every Monday at 9" needs an outside trigger.
- Upgrades that change product behaviour (a renamed API with no equivalent, a
  removed feature) need a human decision. The swarm asks; it does not guess.

## To prove in the first build (Switch behaviours not yet tested here)

- Template-created agents receive scoped GitHub grants (`connections` with
  `repos`).
- One agent can download a patch another agent attached in the same room.
- The foreman can wake workers with targeted messages under `owner-agents`.
- The gate's question card renders in the chat app, and only the lead's answer
  counts.
- Several agent sessions run in parallel on one machine without hitting rate
  limits.
