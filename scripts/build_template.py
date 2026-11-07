#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Build a Switch template for a Backlog Swarm from a fleet file.

    uv run scripts/build_template.py fleet.yml > swarm.template.yaml

The template is version 2 of Switch's template language: one form in Switch
Console creates the room, the foreman, the workers, the verifier and the gate,
with each agent's GitHub access scoped to the fleet's repositories.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
PROVIDERS = {"claude", "codex", "opencode", "antigravity", "cursor"}
CARD_PROVIDERS = {"claude", "opencode", "antigravity"}


class Block(str):
    """A string written as a YAML literal block."""


def block_representer(dumper: yaml.SafeDumper, value: Block) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(value), style="|")


yaml.SafeDumper.add_representer(Block, block_representer)


def fail(message: str) -> None:
    sys.exit(f"build_template: {message}")


def load_fleet(path: Path) -> dict:
    fleet = yaml.safe_load(path.read_text()) or {}
    name = fleet.get("name", "swarm")
    if not NAME.match(name):
        fail(f"name {name!r} must be lowercase letters, digits, '.', '-' or '_'")
    repos = fleet.get("repos") or []
    if not repos:
        fail("repos: list at least one owner/name")
    for repo in repos:
        if not REPO.match(repo):
            fail(f"repos: {repo!r} is not owner/name")
    agents = fleet.get("agents") or {}
    workers = agents.get("workers") or ["codex", "codex"]
    roles = {
        "foreman": agents.get("foreman", "claude"),
        "verifier": agents.get("verifier", "claude"),
        "gate": agents.get("gate", "claude"),
    }
    for role, provider in [*roles.items(), *(("worker", w) for w in workers)]:
        if provider not in PROVIDERS:
            fail(f"agents: {role} provider {provider!r} is not one of {sorted(PROVIDERS)}")
    if roles["gate"] not in CARD_PROVIDERS:
        fail(f"agents: the gate needs native question cards: one of {sorted(CARD_PROVIDERS)}")
    if roles["verifier"] in workers:
        print(
            f"build_template: warning: the verifier ({roles['verifier']}) is the same vendor "
            "as a worker; a different vendor catches more",
            file=sys.stderr,
        )
    return {
        "name": name,
        "toolkit": fleet.get("toolkit", "https://github.com/hassaansaleem28/backlog-swarm"),
        "severities": fleet.get("severities") or ["critical", "high"],
        "repos": repos,
        "roles": roles,
        "workers": workers,
    }


def instructions(role: str) -> Block:
    brief = (AGENTS / f"{role}.md").read_text().strip()
    protocol = (AGENTS / "protocol.md").read_text().strip()
    return Block(f"{brief}\n\n## How this room works\n\n{protocol}\n")


def agent(fleet: dict, key: str, role: str, display: str, provider_param: str,
          addressing: str, access: str, description: str) -> dict:
    return {
        "type": "agent",
        "name": f"{fleet['name']}-{key.replace('_', '-')}",
        "display_name": display,
        "description": description,
        "instructions": instructions(role),
        "provider": f"{{{provider_param}}}",
        "machine": "{machine}",
        "directory": f"{{$agents_dir}}/{{{key}.name}}",
        "repo": fleet["toolkit"],
        "addressing": addressing,
        "auto_approve": [{"if": "{unattended}", "value": True}, {"value": False}],
        "connections": [{"service": "github", "access": access, "repos": fleet["repos"]}],
    }


def fleet_document(fleet: dict, keys: dict[str, str]) -> Block:
    lines = [
        "# Fleet",
        "",
        f"Severities a plain sweep fixes: {', '.join(fleet['severities'])}",
        f"Toolkit: {fleet['toolkit']}",
        "Lead: {$creator}, who created this room. Only the lead can address the gate.",
        "",
        "## Repositories",
        "",
        *(f"- {repo}" for repo in fleet["repos"]),
        "",
        "## Swarm",
        "",
        f"- Foreman: {{{keys['foreman']}.name}}",
        *(f"- Worker: {{{k}.name}}" for k in keys["workers"]),
        f"- Verifier: {{{keys['verifier']}.name}}",
        f"- Gate: {{{keys['gate']}.name}}",
    ]
    return Block("\n".join(lines) + "\n")


def build(fleet: dict) -> dict:
    worker_keys = [f"worker_{i}" for i in range(1, len(fleet["workers"]) + 1)]
    keys = {"foreman": "foreman", "verifier": "verifier", "gate": "gate", "workers": worker_keys}

    params: dict = {
        "bridge": {
            "type": "bridge",
            "label": "Messaging app",
            "description": "Where the swarm's room is created.",
            "default": ["Slack", "$first"],
        },
        "machine": {
            "type": "machine",
            "description": "The machine the agents run on.",
            "default": ["$first"],
            "input": "advanced",
        },
        "unattended": {
            "type": "boolean",
            "label": "Run unattended",
            "description": (
                "Let the foreman, workers and verifier run commands without asking. They hold "
                "read-only GitHub access; run them on a machine you would let them install "
                "packages on. The gate always asks."
            ),
            "default": False,
            "input": "advanced",
        },
    }
    roles = [("foreman", fleet["roles"]["foreman"]), *((k, p) for k, p in zip(worker_keys, fleet["workers"])),
             ("verifier", fleet["roles"]["verifier"]), ("gate", fleet["roles"]["gate"])]
    for key, provider in roles:
        params[f"{key}_provider"] = {
            "type": "provider",
            "label": f"{key.replace('_', ' ').capitalize()} runs on",
            "default": [provider],
            "input": "advanced",
        }

    resources: dict = {
        "foreman": agent(
            fleet, "foreman", "foreman", "Foreman", "foreman_provider", "owner-agents", "read",
            "Plans each Backlog Swarm run, hands out the work and keeps the run report.",
        )
    }
    for index, key in enumerate(worker_keys, start=1):
        resources[key] = agent(
            fleet, key, "worker", f"Worker {index}", f"{key}_provider", "owner-agents", "read",
            "Fixes one repository at a time on its own machine and hands back a patch.",
        )
    resources["verifier"] = agent(
        fleet, "verifier", "verifier", "Verifier", "verifier_provider", "owner-agents", "read",
        "Re-runs every patch from scratch and catches faked fixes.",
    )
    resources["gate"] = agent(
        fleet, "gate", "gate", "Gate", "gate_provider", "owner", "write",
        "Ships verified patches as pull requests, only on the lead's approval.",
    )
    resources["gate"]["auto_approve"] = False
    all_agents = ["foreman", *worker_keys, "verifier", "gate"]
    resources["room"] = {
        "type": "room",
        "name": fleet["name"],
        "description": "Backlog Swarm: AI agents clear the fleet's maintenance backlog; the lead approves.",
        "channel_type": "channel_private",
        "bridge": "{bridge}",
        "agents": all_agents,
        "users": [{"if": "{bridge}", "value": ["{$creator}"]}, {"value": []}],
        "instructions": Block((AGENTS / "protocol.md").read_text()),
        "docs": [
            {
                "name": "Fleet",
                "description": "The repositories, the swarm and the lead.",
                "instructions": "Read at the start of every run. Only the lead changes it.",
                "content": fleet_document(fleet, keys),
            }
        ],
        "kickoff": Block(
            "@{foreman.name} hi. Read the Fleet document and introduce the swarm in "
            "three lines: who is here, what each does, and how I start a sweep.\n"
        ),
    }

    return {
        "version": 2,
        "params": params,
        "form": {"advanced": {"label": "Advanced", "open": False}},
        "resources": resources,
    }


HEADER = """\
# Backlog Swarm: a team of AI agents that clears maintenance work across a
# fleet of repositories, built on Switch. Generated by scripts/build_template.py
# from a fleet file; edit the fleet file and rebuild rather than editing this.
#
# Paste it into Switch Console (Templates, New). It needs a Switch server with
# agent management, and a GitHub connection whose app reaches every repository.
"""


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: build_template.py <fleet.yml>")
    fleet = load_fleet(Path(sys.argv[1]))
    document = build(fleet)
    sys.stdout.write(HEADER)
    sys.stdout.write(yaml.safe_dump(document, sort_keys=False, width=100, allow_unicode=True))


if __name__ == "__main__":
    main()
