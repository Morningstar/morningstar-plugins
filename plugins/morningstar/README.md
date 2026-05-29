# Morningstar Plugin

The Morningstar plugin extends AI coding and research assistants with the ability to perform investment research and analysis using Morningstar's proprietary data and ratings. It gives the assistant access to the same institutional-grade financial data that professional analysts rely on — covering equities and funds — and layers analytical reasoning on top of it to fetch insights.

## MCP Server

Connects to the Morningstar MCP server at `https://mcp.morningstar.com/mcp`. A Morningstar Direct subscription or MCP server license is required — you will be prompted to authenticate on first use.

## Layout

Compatible with **Claude** (Anthropic) and **Codex** (OpenAI). Both share the same plugin source under `plugins/morningstar/` — only the host-specific manifests and install entry points differ.

```text
.agents/plugins/marketplace.json   # Codex marketplace manifest
.claude-plugin/marketplace.json    # Claude marketplace manifest
plugins/
  morningstar/                       # shared plugin source
    .codex-plugin/plugin.json        # Codex plugin manifest
    .claude-plugin/plugin.json       # Claude plugin manifest
    .mcp.json                        # MCP server config
    skills/                          # shared skills (Codex + Claude)
```

---