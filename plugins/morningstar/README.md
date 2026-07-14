# Morningstar Plugin

The Morningstar plugin enables financial analysis using Morningstar’s proprietary data and research through the Morningstar MCP server.

## Skills

- `fund-screener` - screen funds and ETFs with normalized Morningstar criteria.
- `fund-summarizer` - produce factual fund summaries and reports.
- `fund-comparison` - compare 2 to 4 funds side by side.
- `datapoint-finder` - find official Morningstar datapoint names using topic-organized buckets.

The top-level skills intentionally stay lightweight and route data access through the Morningstar app instead of bundling a separate MCP server. Detailed partner-authored workflow rules live in each skill's `references/full-workflow.md`; the fund summary HTML report support files live under `fund-summarizer/assets/`, `fund-summarizer/references/`, and `fund-summarizer/scripts/`.

Fund summary report rendering always writes the HTML report and attempts a sibling PDF copy when the local environment supports it. Existing rendered HTML files can also be exported directly with `fund-summarizer/scripts/export_report.py`.
