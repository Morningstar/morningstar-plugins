## Prerequisites

```bash
pip install python-dateutil
```

---

## Step-by-Step Workflow

### Step 1 — Resolve the fund to a morningstar_id

The host agent calls `morningstar-id-lookup-tool` and passes the result here.

```python
# lookup_results is provided by the host agent from morningstar-id-lookup-tool.
# Shape: [{"morningstar_id": "...", "investment_name": "...", "ticker": "...", ...}]

if not lookup_results:
    print("No funds found. Please try the exact ticker, full legal name, or Morningstar ID.")

elif len(lookup_results) == 1:
    r = lookup_results[0]
    ticker = f" ({r['ticker']})" if r.get('ticker') else ""
    print(f"Found: {r['investment_name']}{ticker}  |  ID: {r['morningstar_id']}")
    # ONE result — proceed directly to Step 2 with r['morningstar_id']

else:
    # MULTIPLE results — show numbered list and STOP; wait for user to choose
    print("Multiple funds found. Please select one by entering its number:\n")
    for i, r in enumerate(lookup_results, 1):
        ticker  = f" ({r['ticker']})" if r.get('ticker') else ""
        itype   = r.get('investment_type', '')
        exch    = r.get('exchange', '')
        meta    = " | ".join(filter(None, [itype, exch]))
        print(f"  {i}. {r['investment_name']}{ticker}  —  {meta}  |  ID: {r['morningstar_id']}")
    print("\nEnter the number of the fund you want to analyze.")
    # STOP HERE — do not proceed to Step 2 until the user replies with their selection
```

- **One result** → proceed directly to Step 2 with that `morningstar_id`
- **Multiple results** → display the numbered list, ask the user to choose, **then wait** — do not fetch until the user replies
- **User gives a Morningstar ID directly** → skip to Step 2

---

### Step 2 — Fetch and normalize fund data

The host agent calls all three MCP tools and passes the raw payloads to `build_data()`.

**Important:** 
  Use `morningstar-data-tool` for historical ratings and pillar timelines. 
  The historical datapoint IDs are `MMR00` for overall Medalist Rating, `MMR1H` for Parent, `MMR2H` for People, `MMR3H` for Process, and `MMRGS` for Price. 
  The rating/pillar assignment-type IDs are `MMRMT` for overall rating type, `MMR1I` for Parent type, `MMR2I` for People type, and `MMR3I` for Process type. 
  Do not attempt to parse historical pillar scores from analyst research text or current datapoints.

| # | MCP Tool (called by host agent) | Purpose |
|---|---------------------------------|---------|
| 1 | `morningstar-id-lookup-tool` (with `datapoints`) | Discover datapoint IDs for current rating, pillars, fees |
| 2 | `morningstar-analyst-research-tool` | Fetch analyst narrative text for all pillars |
| 3 | `morningstar-data-tool` (current + historical IDs) | Fetch structured current values, fees, and historical monthly overall + pillar timelines |

```python
import sys
import io
sys.path.insert(0, 'skills/medalist-rating-analyzer/tools')

# Set UTF-8 encoding for stdout (required on Windows for Unicode symbols like ≥, ×)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from data_normalizer import build_data
from formatter import Formatter

# All raw payloads are provided by the host agent:
#   lookup        — dict from morningstar-id-lookup-tool (the chosen result)
#   research_raw  — dict from morningstar-analyst-research-tool
#   datapoints_raw — dict from morningstar-data-tool (current datapoints)
#   history_raw   — dict from morningstar-data-tool (historical: MMR00/MMR1H/MMR2H/MMR3H/MMRGS)

morningstar_id = lookup['morningstar_id']   # from Step 1

data = build_data(
    lookup=lookup,
    research_raw=research_raw,
    datapoints_raw=datapoints_raw,
    history_raw=history_raw,
    morningstar_id=morningstar_id,
)

fmt = Formatter()

# Check for errors
if isinstance(data, dict) and data.get('error'):
    print("Error: " + str(data['error']))
else:
    
    investment_type = data.get('investment_type')
    
    # >>> YOUR DECISION: Based on the investment_type value, determine if this fund is covered.
    # >>> Set is_covered = True if the investment type semantically matches one of the 7 covered types above.
    # >>> Set is_covered = False if it clearly represents a different vehicle type (e.g., closed-end fund, hedge fund, private fund).
    # >>> If investment_type is None or unclear, set is_covered = True.
    
    # Example decision logic (you should evaluate based on actual investment_type value):
    is_covered = True  # Default to covered if investment_type is missing
    
    if investment_type:
        # Make your semantic matching decision here based on the actual value
        # For example, if investment_type is "Closed-End Fund", set is_covered = False
        # If investment_type is "ETF" or "Mutual Fund", set is_covered = True
        pass  # Replace this with your actual decision logic
    
    if not is_covered:
        # Fund is not covered - show basic info and friendly message
        fund_info = data.get('fund_info', [])
        print("This fund is not covered by current Morningstar Medalist Rating.\n")
        print("Fund Information:")
        for item in fund_info:
            if isinstance(item, dict):
                attr = item.get('Attribute', '')
                val = item.get('Value', '')
                if attr in ['Share Class Name', 'Ticker', 'Morningstar ID', 'Investment Type'] or attr == 'Domicile':
                    print(f"  {attr}: {val}")
    else:
        # Fund is covered - show full report
        # Note: Disclosure is automatically handled by fmt.full_report() based on data['disclosure_type']
        header = fmt.fund_header(data)
        body   = fmt.full_report(data)
        output = header + "\n\n" + body if header else body
        print(output)
```

**`data` now contains everything.** Keep it in context for all follow-up questions.

**How the tools contribute:**
- `morningstar-id-lookup-tool` (with `datapoints=["Morningstar Medalist Rating", "People Pillar", ...]`) discovers the datapoint IDs needed by `morningstar-data-tool`. 
- Confirmed current IDs: `MMR01` = Medalist Rating, `MMR2E` = People Pillar, `MMR3E` = Process Pillar, `MMR1E` = Parent Pillar, `MMRGS` = Price Pillar.
- `morningstar-analyst-research-tool` provides narrative text for each pillar section (People, Process, Parent, Price, overall analysis).
- `morningstar-data-tool` returns structured current values — medal (Gold/Silver/Bronze/Neutral/Negative), current pillar scores (-2 to +2), fees, and historical overall/pillar timelines. These overwrite text-parsed estimates.

### Datapoint IDs (reference: `tools/data_normalizer.py`)

Use these IDs when reasoning about current vs historical pillar scores:

| Metric                                      | Datapoint ID | Source |
|---------------------------------------------|--------------|--------|
| Medalist Rating (overall, current)          | `MMR01` | `morningstar-data-tool` |
| People Pillar (current)                     | `MMR2E` | `morningstar-data-tool` |
| Process Pillar (current)                    | `MMR3E` | `morningstar-data-tool` |
| Parent Pillar (current)                     | `MMR1E` | `morningstar-data-tool` |
| Price Pillar (current)                      | `MMRGS` | `morningstar-data-tool` |
| Historical overall Medalist Rating timeline | `MMR00` | `morningstar-data-tool` |
| Historical Parent pillar timeline           | `MMR1H` | `morningstar-data-tool` |
| Historical People pillar timeline           | `MMR2H` | `morningstar-data-tool` |
| Historical Process pillar timeline          | `MMR3H` | `morningstar-data-tool` |
| Historical Price pillar timeline            | `MMRGS` | `morningstar-data-tool` |
| Historical overall Medalist Rating Type     | `MMRMT` | `morningstar-data-tool` |
| Historical Process Pillar Type              | `MMR3I` | `morningstar-data-tool` |
| Historical People Pillar Type               | `MMR2I` | `morningstar-data-tool` |
| Historical Parent Pillar Type               | `MMR1I` | `morningstar-data-tool` |
| Fund Domicile Country                       | `LS017` | `morningstar-data-tool` |
| Is Index Fund                               | `OF00C` | `morningstar-data-tool` |
| Is Australian Superannuation Fund           | `OS280` | `morningstar-data-tool` |
| Investment Type                             | `LS466` | `morningstar-data-tool` |
| Disclosure Type                             | `CNAXS` | `morningstar-data-tool` |

Rule: use `morningstar-data-tool` for all historical rating questions (overall + pillars).

> **Internal rating formula selection (domicile-aware):** Use `data["domicile_country"]`, `data["is_index_fund"]`, and `data["is_australian_superannuation_fund"]` in this order:
> 1. If domicile is **not Australia (`AUS`)**: use `is_index_fund` only (`True` → Passive, `False`/`None` → Active).
> 2. If domicile **is Australia (`AUS`)**:
>    - If `is_australian_superannuation_fund` is missing/unknown, your **entire response MUST be exactly two sentences**, word-for-word: "Is this an Australian superannuation fund? I need this information to determine how the rating is calculated." (No other text; do not name any formulas.)
>    - If `is_australian_superannuation_fund` is `True`, use the Superannuation formula.
>    - If `is_australian_superannuation_fund` is `False`, use the active/passive split based on `is_index_fund` as in step 1.

### Do / Don't (historical pillar scores)

- **Don't:** use MCP current datapoints or `fmt.*` methods alone for historical People/Process/Parent pillar timeline answers.
- **Do:** call MCP tool (morningstar-data-tool, `MMR00` + `MMR1H`/`MMR2H`/`MMR3H`/`MMRGS` + `MMRMT`/`MMR1I`/`MMR2I`/`MMR3I`) for full historical overall + pillar history including assignment types.
- **Do:** always call MCP tool (morningstar-data-tool, `LS017` + `OF00C` + `OS280`) for fund attributes that determine the correct rating formula — do not attempt to infer from analyst research text or current datapoints.

### MCP historical datapoint request contract

Use this MCP JSON-RPC request shape for historical ratings:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "morningstar-data-tool",
    "arguments": {
      "investment_ids": ["FOUSA00L8W"],
      "datapoint_ids": ["MMR00", "MMR1H", "MMR2H", "MMR3H", "MMRGS", "MMRMT", "MMR3I", "MMR2I", "MMR1I"],
      "start_date": "2025-01-01",
      "end_date": "2026-01-01"
    }
  }
}
```

Default date range when the user does not supply one:
- `end_date` = last month-end relative to today
- `start_date` = 3 years before `end_date`

---

## Answering Follow-up Questions

Once `data` is fetched, apply the matching formatter method or tool to answer any question:

| User asks about | Action                                                                                              |
|----------------|-----------------------------------------------------------------------------------------------------|
| full analysis / overview | `fmt.full_report(data)` — **must include all narrative text**                                       |
| overall rating / rating breakdown | `fmt.overall_rating(data)` — shows current Medalist Rating with type, and latest pillar scores each with their assignment type |
| rating history / overall historical ratings | If fund data with history is in context, present it directly. Otherwise, call `morningstar-data-tool` with historical IDs (`MMR00`,`MMR1H`,`MMR2H`,`MMR3H`,`MMRGS`,`MMRMT`,`MMR1I`,`MMR2I`,`MMR3I`) and show output verbatim including all type labels |
| rating change explanation / why rating changed | If fund data with history is in context, analyze directly using that data. Otherwise, call `morningstar-data-tool` with historical IDs and provide a **quantitative** explanation using pillar and fee changes with the correct weighted formula (Active/Passive/Superannuation) |
| price score / fees | `fmt.price_score(data)`                                                                             |
| people pillar (current) | `fmt.people_pillar(data)`                                                                           |
| process pillar (current) | `fmt.process_pillar(data)`                                                                          |
| parent pillar (current) | `fmt.parent_pillar(data)`                                                                           |
| how Parent/People/Process pillar is calculated (current inputs) | Call `morningstar-data-tool` with current pillar input datapoint IDs from `tools/pillar_rating_input_data.xlsx` (use `get_pillar_data_id` tool to query by pillar and management type), then render as a markdown table with header `Name | Latest Value`. Exception: for **People pillar** on a **passive-managed** fund, answer directly from **Passive People** in the Core Methodology (no input data ID/value lookup). |
| product info / fund identity | `fmt.product_info(data)`                                                                            |
| **historical People/Process/Parent pillar scores** | **Call `morningstar-data-tool` with `MMR00` + `MMR1H`/`MMR2H`/`MMR3H`/`MMRGS` + `MMRMT`/`MMR1I`/`MMR2I`/`MMR3I`, `start_date` and `end_date` |

### Current Pillar Input Datapoints (Parent / People / Process)

When the user asks how a **current** Parent, People, or Process pillar score/rating is calculated for a specific fund:

**Tool-call order is mandatory for this flow:**
- First, ensure the fund has been resolved and fetched (Steps 1 and 2).
- Only after fund context is available, decide whether a second data call is needed.
- If the fund is passive-managed and the user asks about the People pillar, answer directly from the Core Methodology (`Passive People`) and do not use input datapoints.
- For all other cases (Parent/Process pillar, or People pillar on an active-managed fund), use the `get_pillar_data_id` tool to get the specific input datapoint IDs for that pillar and management type, then call `morningstar-data-tool` to get latest values, and render those in a markdown table.
- Never issue pillar-input datapoint retrieval before the fund fetch is complete.

1. If the requested pillar is **People** and the fund is **passive-managed**, answer directly from **Passive People** in the Core Methodology and do **not** find input data ID/value.
2. Otherwise, use the `get_pillar_data_id(pillar, manage_type)` tool from `tools/pillar_data_query.py` to load datapoint IDs for the requested pillar and management type (based on the fund's `is_index_fund` attribute: `True` → "passive", `False` → "active").
3. Call `morningstar-data-tool` once with those datapoint IDs and the selected `morningstar_id`.
4. For Process pillar, query both Active and Passive datapoints using two separate calls to `get_pillar_data_id("process", "active")` and `get_pillar_data_id("process", "passive")`, then merge the results (do not branch on `is_index_fund`, and do not ask the user to choose).
5. Return output as a markdown table with this exact header:

| Name | Latest Value |
|------|--------------|

6. Show all returned datapoints for that pillar and use `N/A` for missing values.
7. Do **not** include any total, sum, or aggregated score row (e.g. "Total Raw Score") in the output — show individual input datapoint values only.
8. This workflow is for **current/latest** values only (not historical pillar timelines).

> **Important:** For any question about how People, Process, Parent, Price or Medalist Rating have changed over time:
> - **If historical rating data is already in context,** answer directly from that context without calling tools.
> - **If historical rating data is NOT in context,** call `morningstar-data-tool` with the fund's `morningstar_id` and the historical IDs (`MMR00`,`MMR1H`,`MMR2H`,`MMR3H`,`MMRGS`,`MMRMT`,`MMR1I`,`MMR2I`,`MMR3I`). 
> After calling the tool, present its output **verbatim**: do not reformat into a markdown table, do not summarize, and do not omit any rating type labels (e.g. `Analyst Assigned`, `Algorithmic`, `Quantitative`). Those type labels are a required part of the response.

### Special Rule — Rating Change Explanation Questions

When the user asks why a fund's rating changed (or asks to explain rating changes over time), apply all rules below:

1. **Use quantitative methodology:**
   - Use historical pillar values plus price/fee changes.
   - Load "medalist-rating-methodology" skill and apply the correct weighted formula (Active/Passive/Superannuation) based on the fund's attributes (`domicile_country`, `is_index_fund`, `is_australian_superannuation_fund`).
   - Show a quantitative assessment (direction and contribution by component) rather than only qualitative narrative.

2. **Date limitation for legacy periods:**
   - Rating changes **before April 2026** cannot be fully explained in details with the current methodology.
   - Exception: if a specific pre-April 2026 change is discussed in analyst research (`morningstar-analyst-research-tool`), include that research-based explanation.

3. **Required general response for old periods:**
   - For rating changes **before April 2026**, if there is no pillar rating change at same time, use this general response:
   - "The rating calculation before April 2026 was different than the current methodology. I do not have access the previous methodology at this moment"

All time-series methods accept optional `start_date` and `end_date` keyword arguments.

---

## Date Range Filtering

Every time-series formatter method accepts `start_date` and `end_date` as optional keyword arguments.

| What the user says | How to call |
|--------------------|-------------|
| "since January 2022" | `start_date="January 2022"` |
| "from June 2020 to December 2022" | `start_date="June 2020", end_date="December 2022"` |
| "in 2021" | `start_date="2021-01-01", end_date="2021-12-31"` |
| "up to 2023" | `end_date="2023"` |

### Supported methods

All of these accept `start_date` / `end_date`:
- `fmt.historical_ratings(data, start_date=..., end_date=...)`
- `fmt.overall_rating(data, start_date=..., end_date=...)`
- `fmt.price_score(data, start_date=..., end_date=...)`
- `fmt.people_pillar(data, start_date=..., end_date=...)`
- `fmt.process_pillar(data, start_date=..., end_date=...)`
- `fmt.parent_pillar(data, start_date=..., end_date=...)`
- `fmt.full_report(data, start_date=..., end_date=...)` — applies the filter to **all** sections

### Date filtering examples

**Show rating history since January 2024:**
```python
import sys, io
sys.path.insert(0, 'skills/medalist-rating-analyzer/tools')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from formatter import Formatter
fmt = Formatter()
# data is already in context
header = fmt.fund_header(data)
body   = fmt.historical_ratings(data, start_date="January 2024")
output = header + "\n\n" + body if header else body
print(output)
```
## Follow-up Question Examples

**Show people pillar:**
```python
import sys, io
sys.path.insert(0, 'skills/medalist-rating-analyzer/tools')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from formatter import Formatter
fmt = Formatter()
# data is already in context from Step 2
header = fmt.fund_header(data)
body   = fmt.people_pillar(data)
output = header + "\n\n" + body if header else body
print(output)
```

## Behavior Rules

- **Fetch once, answer many.** After Step 2 succeeds, answer all follow-up questions about the same fund from `data` — never re-fetch for the same fund in the same session.
- **Investment type coverage check.** After fetching fund data, evaluate whether `data["investment_type"]` semantically matches one of these 7 covered vehicle types: (1) Open-end mutual funds, (2) ETFs, (3) Separate accounts, (4) Model portfolios, (5) Variable annuity/life subaccounts, (6) Collective Investment Trusts (CITs), (7) Australian superannuation vehicles. Use meaning-based matching (consider abbreviations, singular/plural, case variations). If the fund is NOT covered, show only basic fund information (name, ticker, security id, domicile country, and investment type) with the message: "This fund is not covered by current Morningstar Medalist Rating." Do not show rating or pillar analysis for uncovered types. If investment_type is missing/None, assume the fund IS covered.
- **Show complete output.** Never truncate or summarize formatter output — return it in full.
- **Complete analysis includes all narrative text.** When generating a full analysis (`fmt.full_report(data)`), the response **must** contain every narrative text field present in `data`:
  - `data["rating_breakdown"]["derivation_text"]` — overall analysis narrative
  - `data["price"]["text"]` — price score narrative
  - `data["people_pillar"]["text"]` — People pillar narrative
  - `data["process_pillar"]["text"]` — Process pillar narrative
  - `data["parent_pillar"]["text"]` — Parent pillar narrative
- **Fund switched.** When the user asks about a different fund, run Steps 1 and 2 again for the new fund. Replace `data` with the new response.
- **No results from lookup.** Ask the user to try the exact ticker, full legal name, or Morningstar ID.
- **MCP server unreachable.** Inform the user clearly — there is no offline fallback.
- **Historical MCP datapoints unreachable.** Continue with current MCP-derived data and clearly say historical pillar score history may be incomplete.
- **Empty research results.** If `morningstar-analyst-research-tool` returns no results, pass an empty `research_raw` to `build_data()`; inform the user the full analyst research is not available.
- **Methodology questions.** Use `medalist-rating-methodology` for formulas, rules, and eligibility questions not tied to a specific fund lookup.
- **Disclosure handling.** The formatter automatically handles disclosure display. When `data["disclosure_type"]` is "Issuer Initiated Rating" or "Tracks Morningstar Index", `fmt.full_report()` automatically prepends the appropriate disclosure text at the beginning of the output with separator lines. No manual disclosure handling is needed.
- **Off-topic.** Respond: *"I specialize in Morningstar Medalist Rating analysis. Ask me about a fund by name, ticker, or Morningstar ID."*
- **include the fund name and ticker in all responses** to avoid confusion when the user is asking about multiple funds in the same session.
- **disclosure text** When summarizing, always keep the original disclosure text if present, do not shorten it. Keep the fund name and ticker in the summary.
---

## What the Normalized Data Dict Contains

```python
data = {
    # Identifiers
    "share_class_id": "0P0000006A",   # morningstar_id used as identifier
    "morningstar_id": "0P0000006A",

    # Fund identity (list of {Attribute, Value} rows)
    "fund_info": [
        {"Attribute": "Share Class Name", "Value": "Vanguard 500 Index Fund Admiral"},
        {"Attribute": "Ticker",           "Value": "VFIAX"},
        {"Attribute": "Investment Type",  "Value": "Mutual Fund"},
        {"Attribute": "Exchange",         "Value": "..."},
        {"Attribute": "Morningstar ID",   "Value": "0P0000006A"},
        {"Attribute": "Research Published", "Value": "2025-03-15"},  # if available
        {"Attribute": "Reference URL",    "Value": "https://..."},   # if available
    ],

    # Overall rating (numeric: 2=Gold, 1=Silver, 0=Bronze, -1=Neutral, -2=Negative)
    "overall_rating":  0,
    "rating_symbol":   "●●●◐◯",
    "rating_breakdown": {
        "weighted_score":  None,        # not returned by MCP research
        "formula_text":    "",
        "derivation_text": "...",       # extracted from overall_analysis content
    },

    # Historical ratings (merged from morningstar-data-tool historical datapoints)
    "historical_ratings": [
        {
            "EndDate":                        "2026-03-31",
            "Medalist Rating":                0,            # numeric: 2=Gold … -2=Negative
            "Medalist Rating Type":           "Analyst Assigned",  # MMRMT — string or None
            "Weighted Medalist Rating Score":  -0.1432,
            "People":       0,   "People Type":  "Algorithmic",    # MMR2I — string or None
            "Process":      1,   "Process Type": "Analyst Assigned", # MMR3I — string or None
            "Parent":      -1,   "Parent Type":  "Analyst Assigned", # MMR1I — string or None
            "Price Score":  0,
        },
        # ...
    ],

    # Price
    "medalist_price_score": -1,
    "price": {
        "data": [],
        "text": "Price pillar narrative...",
    },

    # Pillars — narrative from morningstar-analyst-research-tool
    "people_pillar": {
        "data":             [{"PeopleScore": 0, "EndDate": ""}],
        "algorithmic_data": [],
        "text":             "People pillar narrative...",
    },
    "process_pillar": {
        "data":             [{"ProcessScore": 1, "EndDate": ""}],
        "algorithmic_data": [],
        "text":             "Process pillar narrative...",
    },
    "parent_pillar": {
        "data":             [{"ParentScore": -1, "EndDate": ""}],
        "algorithmic_data": [],
        "text":             "Parent pillar narrative...",
    },

    # MCP metadata
    "source":        "mcp",
    "published_at":  "2025-03-15T00:00:00Z",
    "reference_url": "https://www.morningstar.com/...",
    "error":         None,

    # Fund attribute flags — used to select the correct rating methodology formula
    "domicile_country":                 "United States",  # LS017: fund domicile country
    "is_australian_domicile":           False,              # derived from LS017 (True for AUS/Australia)
    "is_index_fund":                    False,  # OF00C: True if fund is an index fund
    "is_australian_superannuation_fund": False, # OS280: True if Australian super fund
    "investment_type":                  "Open-end mutual funds",  # LS466: Investment vehicle type
    "disclosure_type":                  None,   # CNAXS: "Issuer Initiated Rating", "Tracks Morningstar Index", or None
}
```

---

## Available Tools

### get_pillar_data_id

Located in `tools/pillar_data_query.py`, this tool queries the `pillar_rating_input_data.xlsx` workbook to get filtered datapoint IDs.

```python
from tools.pillar_data_query import get_pillar_data_id

# Get Process pillar IDs for Active management
active_process_ids = get_pillar_data_id("process", "active")
# Returns: ['ZS71V', 'ODA4H', 'MVD74', ...]

# Get People pillar IDs for Active management
active_people_ids = get_pillar_data_id("people", "active")
# Returns: ['A9SD3', 'E89P9', 'I4JKP', ...]

# Get Parent pillar IDs for Passive management
passive_parent_ids = get_pillar_data_id("parent", "passive")
# Returns: ['CW7G7', 'DX37P', 'EO0U8', ...]
```

**Parameters:**
- `pillar`: `"parent"`, `"people"`, or `"process"` (case-insensitive)
- `manage_type`: `"active"` or `"passive"` (case-insensitive)

**Returns:** List of datapoint IDs matching the criteria

See `tools/README.md` for detailed usage examples.

**Example usage for fetching current pillar inputs:**

```python
import sys, io
sys.path.insert(0, 'skills/medalist-rating-analyzer/tools')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pillar_data_query import get_pillar_data_id

# For an active-managed fund, get People pillar input IDs
people_ids = get_pillar_data_id("people", "active")

# For Process pillar, merge both Active and Passive datapoints
process_active_ids = get_pillar_data_id("process", "active")
process_passive_ids = get_pillar_data_id("process", "passive")
all_process_ids = process_active_ids + process_passive_ids

# Then call morningstar-data-tool with these IDs to get current values
# (see "Current Pillar Input Datapoints" section above for full workflow)
```

---

## Error Reference

| Condition | Cause | Agent response |
|-----------|-------|----------------|
| `lookup_results` is empty list | Ticker/name not in Morningstar DB | Ask user for exact ticker, full legal name, or Morningstar ID |
| `research_raw` has empty results | Fund has no analyst research | Pass empty payload to `build_data()`; inform user analyst research is not available |