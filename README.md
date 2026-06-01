# Morningstar Plugins

A collection of AI assistant plugins for Morningstar — analytical skills that bring Morningstar's proprietary data, ratings, and research directly into your AI workflow.

Plugins in this repo are compatible with **claude-plugin** (Claude Code) and **codex-plugin** (OpenAI Codex) formats.

## What is a plugin?

A plugin is a shareable package that extends an AI assistant with new capabilities. Plugins can include:

- **Skills** — instructions that teach the assistant a specific analytical workflow, automatically invoked when relevant or triggered directly with `/plugin-name:skill-name`
- **MCP servers** — connections to external data sources and tools
- **Agents and hooks** — custom behaviours and automation

Plugins are namespaced to prevent conflicts. Skills in this repo are invoked as `/morningstar:<skill-name>`.

## Plugins in this repo

| Plugin | Description |
|---|---|
| `morningstar` | Fund screening, comparison, and summarization using Morningstar ratings, returns, risk, and holdings data |

## MCP server

All skills connect to the Morningstar MCP server at `mcp.morningstar.com/mcp`. A Morningstar Direct subscription is required. You will be prompted to authenticate on first use.

## Installation

**Claude Code** — load locally for development:

```sh
claude --plugin-dir ./
```

**Codex** — add the local marketplace and install the plugin:

```sh
codex plugin marketplace add "$(pwd)"
codex plugin add morningstar@morningstar-plugin-marketplace
```

Install from a published marketplace:

```sh
/plugin install morningstar
```

## Updating

After changes are merged into this repo, pull them into your active session in two steps:

**1. Refresh the marketplace catalog** (fetches the latest plugin versions from GitHub):

```sh
/plugin marketplace update <marketplace-name>
```

Replace `<marketplace-name>` with the name you used when adding this marketplace (e.g. the repo slug). If you're unsure of the name, run `/plugin marketplace list` to see all configured marketplaces.

**2. Reload plugins in your active session:**

```sh
/reload-plugins
```

This reloads all active plugins — including updated skills, agents, hooks, MCP servers, and LSP servers — without requiring a restart.

> For local development with `--plugin-dir`, you only need `/reload-plugins` after saving changes; there is no marketplace catalog to refresh.

## Repo structure

```
morningstar-plugins/
├── .claude-plugin/
│   └── marketplace.json        # Claude Code marketplace index
├── .codex-plugin/
│   └── marketplace.json        # Codex marketplace index
└── plugins/
    └── morningstar/            # The Morningstar plugin
        ├── .claude-plugin/
        │   └── plugin.json
        ├── .codex-plugin/
        │   └── plugin.json
        ├── .mcp.json
        ├── README.md
        └── skills/
            ├── fund-summarizer/
            ├── fund-comparison/
            └── fund-screener/
```