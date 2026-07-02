"""
Data Normalizer

Converts raw Morningstar MCP server responses into the structured ``data``
dict that formatter.py already consumes.

Main entry points:
    from data_normalizer import normalize, supplement_with_datapoints, build_data

    # Low-level (step-by-step):
    data = normalize(lookup_result, research_raw, morningstar_id)
    data = supplement_with_datapoints(data, datapoints_raw, datapoint_ids=ids_map)
    merge_historical_rows(data, history_rows)

    # High-level (all pre-fetched payloads at once):
    data = build_data(lookup, research_raw, datapoints_raw, history_raw, morningstar_id)

All functions are pure / stateless — no network calls, no I/O.
The MCP transport and OAuth are handled by the host agent app.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Rating / pillar label mappings
# ---------------------------------------------------------------------------

_MEDAL_TO_INT: dict[str, int] = {
    "gold":     2,
    "silver":   1,
    "bronze":   0,
    "neutral":  -1,
    "negative": -2,
}

_INT_TO_SYMBOL: dict[int, str] = {
    2:  "●●●●●",
    1:  "●●●●◯",
    0:  "●●●◐◯",
    -1: "●●◯◯◯",
    -2: "●◯◯◯◯",
}

_PILLAR_TEXT_TO_INT: dict[str, int] = {
    "high":          2,
    "above average": 1,
    "average":       0,
    "below average": -1,
    "low":           -2,
}


def _strip_quantitative_marker(value: Any) -> Any:
    """Remove Morningstar's ^Q suffix from textual pillar values."""
    if not isinstance(value, str):
        return value
    cleaned = re.sub(r"\s*\^Q\s*", "", value)
    cleaned = cleaned.strip()
    return cleaned if cleaned != "" else None

def _string_or_empty(value: Any) -> str:
    """Return a safe string value for narrative text fields."""
    if value in (None, ""):
        return ""
    return str(value)


def _parse_optional_bool(value: Any) -> bool | None:
    """Parse boolean-like datapoint values; return None when value is unknown/blank."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    return None

# ---------------------------------------------------------------------------
# Datapoint ID registry (public — host agent uses these to build MCP calls)
# ---------------------------------------------------------------------------

KNOWN_DATAPOINT_IDS: dict[str, str] = {
    "MedalistRating":                 "MMR01",  # Morningstar Medalist Rating      → Gold/Silver/Bronze/Neutral/Negative
    "PeoplePillar":                   "MMR2E",  # MM Rating People Pillar           → High/Above Average/Average/...
    "ProcessPillar":                  "MMR3E",  # MM Rating Process Pillar          → High/Above Average/Average/...
    "ParentPillar":                   "MMR1E",  # MM Rating Parent Pillar           → High/Above Average/Average/...
    "PricePillar":                    "MMR4E",  # MM Rating Price Pillar (current snapshot)
    "FundDomicileCountry":            "LS017",  # Domicile                          → country name/code
    "IsIndexFund":                    "OF00C",  # Is Index Fund                     → true/false
    "IsAustralianSuperannuationFund": "OS280",  # Is Australian Superannuation Fund → true/false
    "InvestmentType":                 "LS466",  # Investment Type                   → fund vehicle type
    "DisclosureType":                 "CNAXS",  # Disclosure Type                   → "Issuer Initiated Rating", "Tracks Morningstar Index", or None
}

# Historical time-series datapoint IDs.
HISTORICAL_DATAPOINT_IDS: dict[str, str] = {
    "HistoricalMedalistRating":      "MMR00",
    "HistoricalParentPillar":        "MMR1H",
    "HistoricalPeoplePillar":        "MMR2H",
    "HistoricalProcessPillar":       "MMR3H",
    "HistoricalPricePillar":         "MMRGS",
    # Rating/pillar assignment-type time-series (string labels, not numeric scores)
    "HistoricalMedalistRatingType":  "MMRMT",  # Morningstar Medalist Overall Rating Type
    "HistoricalProcessPillarType":   "MMR3I",  # Morningstar Medalist Rating Process Pillar Type
    "HistoricalPeoplePillarType":    "MMR2I",  # Morningstar Medalist Rating People Pillar Type
    "HistoricalParentPillarType":    "MMR1I",  # Morningstar Medalist Rating Parent Pillar Type
}

# Combined default set used internally by supplement_with_datapoints.
_DEFAULT_DATAPOINT_IDS: dict[str, str] = {
    **KNOWN_DATAPOINT_IDS,
}

# Search terms sent to morningstar-id-lookup-tool for live datapoint discovery.
STANDARD_DATAPOINT_NAMES: list[str] = [
    "Morningstar Medalist Rating",    # → MMR01
    "People Pillar",                  # → MMR2E
    "Process Pillar",                 # → MMR3E
    "Parent Pillar",                  # → MMR1E
    "Price Pillar",                   # → MMRGS
    "Domicile",                       # → LS017
]

# ---------------------------------------------------------------------------
# Default historical date-range helper
# ---------------------------------------------------------------------------

def default_historical_range() -> tuple[str, str]:
    """Return a default 3-year historical date range ending at last month-end."""
    today = date.today()
    first_of_month = today.replace(day=1)
    end_date = first_of_month - timedelta(days=1)
    try:
        start_date = end_date.replace(year=end_date.year - 3)
    except ValueError:
        start_date = end_date - timedelta(days=1)
        start_date = start_date.replace(year=start_date.year - 3)
    return start_date.isoformat(), end_date.isoformat()


# ---------------------------------------------------------------------------
# Regex helpers for parsing MCP research text content
# ---------------------------------------------------------------------------

_MEDAL_RE = re.compile(
    r"\b(Gold|Silver|Bronze|Neutral|Negative)\b"
    r"(?:\s+Medalist|\s+Rating|\s+rated)?",
    re.IGNORECASE,
)

_PILLAR_RATING_RE = re.compile(
    r"\b(High|Above Average|Average|Below Average|Low)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Low-level text extraction helpers (for analyst research content)
# ---------------------------------------------------------------------------

def _concat_content(results: list[dict]) -> str:
    return " ".join(r.get("content", "") for r in results)


def _extract_value(key: str, text: str, max_chars: int = 2000) -> str:
    """Extract the value for a JSON key from the MCP content string."""
    pattern = re.compile(
        re.escape(f'"{key}":') + r'\s*"(.*?)(?:(?<=[^\\])",\s*"|"[,}\s])',
        re.DOTALL,
    )
    m = pattern.search(text)
    if m:
        val = m.group(1)
        val = re.sub(r"\\u([0-9a-fA-F]{4})", lambda x: chr(int(x.group(1), 16)), val)
        val = val.replace("\\n", "\n").replace("\\t", " ")
        return val[:max_chars]
    idx = text.find(f'"{key}":')
    if idx == -1:
        return ""
    snippet = text[idx + len(key) + 4: idx + len(key) + 4 + max_chars]
    snippet = snippet.lstrip(' "')
    return snippet.split('"')[0] if '"' in snippet else snippet


def _detect_medal(text: str) -> int | None:
    hits = _MEDAL_RE.findall(text)
    if hits:
        return _MEDAL_TO_INT.get(hits[0].lower())
    return None


def _detect_pillar_score(text: str) -> int | None:
    m = _PILLAR_RATING_RE.search(text)
    if m:
        return _PILLAR_TEXT_TO_INT.get(m.group(1).lower())
    return None


# ---------------------------------------------------------------------------
# fund_info builder
# ---------------------------------------------------------------------------

def _build_fund_info(lookup: dict, morningstar_id: str) -> list[dict]:
    rows = []
    name     = lookup.get("investment_name", "")
    ticker   = lookup.get("ticker", "")
    itype    = lookup.get("investment_type", "")
    exchange = lookup.get("exchange", "")

    if name:
        rows.append({"Attribute": "Share Class Name", "Value": name})
    if ticker:
        rows.append({"Attribute": "Ticker", "Value": ticker})
    if itype:
        rows.append({"Attribute": "Investment Type", "Value": itype})
    if exchange:
        rows.append({"Attribute": "Exchange", "Value": exchange})
    rows.append({"Attribute": "Morningstar ID", "Value": morningstar_id})
    return rows


def _set_fund_info_value(data: dict, attr: str, value: Any) -> None:
    """Upsert an Attribute/Value row in fund_info."""
    if value in (None, ""):
        return
    rows = data.setdefault("fund_info", [])
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict) and row.get("Attribute") == attr:
            row["Value"] = value
            return
    rows.append({"Attribute": attr, "Value": value})


def _is_australia_domicile(value: Any) -> bool | None:
    """Return True/False when domicile is known, else None."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    normalized = raw.replace(" ", "")
    if normalized in ("aus", "au", "australia") or "australia" in raw:
        return True
    return False


# ---------------------------------------------------------------------------
# Pillar / price narrative extraction from analyst research text
# ---------------------------------------------------------------------------

_PILLAR_CONTENT_KEYS: dict[str, list[str]] = {
    "people_pillar":  ["People", "people_pillar_analysis", "People Pillar"],
    "process_pillar": ["Investment Process", "process_pillar_analysis", "Process Pillar"],
    "parent_pillar":  ["parent_pillar_analysis", "Parent", "Parent Pillar"],
}
_PRICE_CONTENT_KEYS   = ["Fund Price", "price_pillar_analysis", "Price", "Price Pillar"]
_OVERALL_CONTENT_KEYS = ["overall_analysis", "Overall Analysis", "Medalist Rating"]


def _extract_pillars(content: str) -> dict[str, dict]:
    pillars: dict[str, dict] = {}
    for pillar_key, keys in _PILLAR_CONTENT_KEYS.items():
        text  = ""
        score = None
        for k in keys:
            val = _extract_value(k, content, max_chars=3000)
            if val:
                text  = val
                score = _detect_pillar_score(val)
                break
        score_key = "{}Score".format(pillar_key.split("_")[0].capitalize())
        pillars[pillar_key] = {
            "data":             [{score_key: score, "EndDate": ""}] if score is not None else [],
            "algorithmic_data": [],
            "text":             text,
        }
    return pillars


def _extract_price(content: str) -> tuple[dict, int | None]:
    text  = ""
    score = None
    for k in _PRICE_CONTENT_KEYS:
        val = _extract_value(k, content, max_chars=2000)
        if val:
            text  = val
            score = _detect_pillar_score(val)
            break
    return {"data": [], "text": text}, score


def _extract_overall(content: str) -> tuple[int | None, str]:
    overall_text = ""
    for k in _OVERALL_CONTENT_KEYS:
        val = _extract_value(k, content, max_chars=2000)
        if val:
            overall_text = val
            break
    medal = _detect_medal(overall_text) if overall_text else _detect_medal(content)
    return medal, overall_text


# ---------------------------------------------------------------------------
# Historical rows helpers
# ---------------------------------------------------------------------------

def _clean_mcp_value(value: Any) -> Any:
    """Preserve the MCP value as-is, trimming only surrounding whitespace on strings."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned != "" else None
    return value


def _try_json(s: str) -> Any:
    import json
    try:
        return json.loads(s)
    except Exception:
        return s


def extract_historical_rows(raw: Any) -> list[dict]:
    """Pivot historical time series into per-date rows while preserving raw MCP values."""
    by_date: dict[str, dict[str, Any]] = {}

    def _record(field: str, series: list) -> None:
        for item in series:
            if not isinstance(item, dict):
                continue
            end_date = str(
                item.get("EndDate") or item.get("endDate") or item.get("End_Date") or
                item.get("Date") or item.get("date") or item.get("asOfDate") or ""
            ).strip()
            if not end_date:
                continue
            raw_val = None
            for key in ("Value", "value", "val"):
                if key in item:
                    raw_val = item.get(key)
                    break
            converted = _clean_mcp_value(raw_val)
            if field in {"People", "Process", "Parent"}:
                converted = _strip_quantitative_marker(converted)
            if converted is None:
                continue
            row = by_date.setdefault(end_date, {"EndDate": end_date})
            row[field] = converted

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            node = _try_json(node)

        if isinstance(node, dict):
            dp_id = str(node.get("datapointId") or node.get("datapoint_id") or "").strip().upper()
            field = {
                "MMR00": "Medalist Rating",
                "MMR1H": "Parent",
                "MMR2H": "People",
                "MMR3H": "Process",
                "MMRGS": "Price Score",
                # Assignment-type fields
                "MMRMT": "Medalist Rating Type",
                "MMR3I": "Process Type",
                "MMR2I": "People Type",
                "MMR1I": "Parent Type",
            }.get(dp_id)
            if field:
                for ts_key in ("timeSeriesData", "TimeSeriesData", "timeSeries", "TimeSeries", "history", "History"):
                    ts = node.get(ts_key)
                    if isinstance(ts, list):
                        _record(field, ts)
                        break

            for value in node.values():
                if isinstance(value, (dict, list)):
                    _walk(value)
            return

        if isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(raw)

    rows = [
        {
            "EndDate":                       d,
            "Medalist Rating":               row.get("Medalist Rating"),
            "Medalist Rating Type":          row.get("Medalist Rating Type"),
            "Weighted Medalist Rating Score": None,
            "People":                        row.get("People"),
            "People Type":                   row.get("People Type"),
            "Process":                       row.get("Process"),
            "Process Type":                  row.get("Process Type"),
            "Parent":                        row.get("Parent"),
            "Parent Type":                   row.get("Parent Type"),
            "Price Score":                   row.get("Price Score"),
        }
        for d, row in by_date.items()
        if any(
            row.get(f) is not None
            for f in (
                "Medalist Rating", "Medalist Rating Type",
                "People", "People Type",
                "Process", "Process Type",
                "Parent", "Parent Type",
                "Price Score",
            )
        )
    ]
    return sorted(rows, key=lambda r: r["EndDate"], reverse=True)


def merge_historical_rows(data: dict, rows: list[dict]) -> None:
    """Merge historical rating rows (from morningstar-data-tool) into normalized data.

    Updates ``data["historical_ratings"]`` in-place and back-fills raw MCP
    snapshot values from the most recent row when current datapoints did not
    return them.
    """
    existing = data.get("historical_ratings") or []
    by_date = {
        str(r.get("EndDate", "")): dict(r)
        for r in existing
        if isinstance(r, dict) and r.get("EndDate")
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        end_date = str(row.get("EndDate", ""))
        if not end_date:
            continue
        merged = dict(by_date.get(end_date, {}))
        for key, value in row.items():
            if value is not None:
                merged[key] = value
        by_date[end_date] = merged

    merged_rows = sorted(by_date.values(), key=lambda r: str(r.get("EndDate", "")), reverse=True)
    if merged_rows:
        data["historical_ratings"] = merged_rows

    latest = merged_rows[0] if merged_rows else None
    if not latest:
        return

    medal = latest.get("Medalist Rating")
    if medal is not None and data.get("overall_rating_raw") is None:
        data["overall_rating_raw"] = medal

    weighted = latest.get("Weighted Medalist Rating Score")
    if weighted is not None:
        breakdown = data.setdefault("rating_breakdown", {})
        if breakdown.get("weighted_score") is None:
            breakdown["weighted_score"] = weighted

    if latest.get("Price Score") is not None and data.get("medalist_price_score") is None:
        data["medalist_price_score"] = latest.get("Price Score")


# ---------------------------------------------------------------------------
# Structured datapoint application helpers
# ---------------------------------------------------------------------------

def _pillar_str_to_int(val: Any) -> int | None:
    """Convert a datapoint value (string label or numeric) to -2..+2 int."""
    if val is None:
        return None
    try:
        n = int(float(str(val)))
        if -2 <= n <= 2:
            return n
    except (ValueError, TypeError):
        pass
    text = str(val).split("^", 1)[0].strip().lower()
    text = "".join(ch for ch in text if ch.isalpha() or ch.isspace()).strip()
    return _PILLAR_TEXT_TO_INT.get(text)


def _build_historical_from_ts(ts: list) -> list[dict]:
    """Build historical_ratings rows from a morningstar-data-tool time-series."""
    hist = []
    for point in ts:
        end_date  = point.get("endDate") or point.get("date") or ""
        raw_val   = _clean_mcp_value(point.get("value"))
        hist.append({
            "EndDate":                        end_date,
            "Medalist Rating":                raw_val,
            "Medalist Rating Type":           None,
            "Weighted Medalist Rating Score":  None,
            "People":       None,
            "People Type":  None,
            "Process":      None,
            "Process Type": None,
            "Parent":       None,
            "Parent Type":  None,
            "Price Score":  None,
        })
    hist.sort(key=lambda r: r["EndDate"], reverse=True)
    return hist


def _apply_datapoint(
    data: dict,
    dp_name: str,
    dp_id: str,
    dp_val: Any,
    ts: list,
) -> None:
    """Apply one morningstar-data-tool datapoint to the normalized data dict.

    dp_name: canonical name from our ids_map (e.g. "MedalistRating").
    dp_id:   raw datapoint ID from the server (e.g. "MMR01").
    dp_val:  current scalar value.
    ts:      timeSeriesData list (may be empty).

    Structured values are AUTHORITATIVE — they overwrite text-parsed estimates.
    """
    nk = (dp_name or "").lower().replace(" ", "").replace("_", "")

    # ── Medalist Rating (medal) ─────────────────────────────────────────────
    if nk in ("medalistrating", "medalistratingoverall") or dp_id == "MMR01":
        raw_val = _clean_mcp_value(dp_val)
        if raw_val is not None:
            data["overall_rating_raw"] = raw_val
            key       = str(raw_val).split("^", 1)[0].lower().strip()
            medal_int = _MEDAL_TO_INT.get(key) if key else None
            if medal_int is None:
                medal_int = _pillar_str_to_int(raw_val)
            if medal_int is not None:
                data["overall_rating"] = medal_int
                data["rating_symbol"]  = _INT_TO_SYMBOL.get(medal_int, "")
        if ts:
            hist = _build_historical_from_ts(ts)
            if hist:
                data["historical_ratings"] = hist

    # ── Weighted Medalist Rating Score ──────────────────────────────────────
    elif nk in ("medalistratingscoreweighted", "medalistratingscore",
                "weightedmedalistratingscore", "medalistratingscoreraw"):
        try:
            ws = float(str(dp_val))
            bd = data.setdefault(
                "rating_breakdown",
                {"weighted_score": None, "formula_text": "", "derivation_text": ""},
            )
            bd["weighted_score"] = ws
        except (TypeError, ValueError):
            pass

    # ── People Pillar ───────────────────────────────────────────────────────
    elif "peoplepillar" in nk or nk == "people" or dp_id == "MMR2E":
        raw_val = _clean_mcp_value(dp_val)
        raw_val = _strip_quantitative_marker(raw_val)
        if raw_val is not None:
            existing_text = _string_or_empty((data.get("people_pillar") or {}).get("text", ""))
            payload: dict[str, Any] = {
                "data":             [{"PeopleScore": raw_val, "PeopleScoreType": "Morningstar Data", "EndDate": ""}],
                "algorithmic_data": [],
                "text":             existing_text,
            }
            data["people_pillar"] = payload

    # ── Process Pillar ──────────────────────────────────────────────────────
    elif "processpillar" in nk or nk in ("process", "investmentprocess") or dp_id == "MMR3E":
        raw_val = _clean_mcp_value(dp_val)
        raw_val = _strip_quantitative_marker(raw_val)
        if raw_val is not None:
            existing_text = ""
            existing_process = data.get("process_pillar")
            if isinstance(existing_process, dict):
                existing_text = _string_or_empty(existing_process.get("text", ""))
            payload: dict[str, Any] = {
                "data":             [{"ProcessScore": raw_val, "ProcessScoreType": "Morningstar Data", "EndDate": ""}],
                "algorithmic_data": [],
                "text":             existing_text,
            }
            data["process_pillar"] = payload

    # ── Parent Pillar ───────────────────────────────────────────────────────
    elif "parentpillar" in nk or nk == "parent" or dp_id == "MMR1E":
        raw_val = _clean_mcp_value(dp_val)
        raw_val = _strip_quantitative_marker(raw_val)
        if raw_val is not None:
            existing_text = _string_or_empty((data.get("parent_pillar") or {}).get("text", ""))
            payload: dict[str, Any] = {
                "data":             [{"ParentScore": raw_val, "ParentScoreType": "Morningstar Data", "EndDate": ""}],
                "algorithmic_data": [],
                "text":             existing_text,
            }
            data["parent_pillar"] = payload

    # ── Price / Fee Pillar ──────────────────────────────────────────────────
    elif "pricepillar" in nk or "pricescore" in nk or nk in ("fundprice", "price", "featuredrating") or dp_id == "MMRGS":
        raw_val = _clean_mcp_value(dp_val)
        if raw_val is not None:
            data["medalist_price_score"] = raw_val

    # ── Annual Fee ──────────────────────────────────────────────────────────
    elif "annualfee" in nk or "annualreportexpense" in nk or (
        ("expense" in nk or "fee" in nk) and "median" not in nk and "category" not in nk
    ):
        try:
            fee = float(str(dp_val))
            price_existing_text = (data.get("price") or {}).get("text", "")
            price = data.setdefault("price", {"data": [], "text": price_existing_text})
            if not price.get("data"):
                price["data"] = [{"AnnualFee": fee, "CategoryMedianAnnualFee": None, "FeeType": "Annual", "EndDate": ""}]
            else:
                price["data"][0]["AnnualFee"] = fee
        except (TypeError, ValueError):
            pass

    # ── Category Median Fee ─────────────────────────────────────────────────
    elif ("categorymedian" in nk or "catmedian" in nk) and ("fee" in nk or "expense" in nk):
        try:
            fee = float(str(dp_val))
            price_existing_text = (data.get("price") or {}).get("text", "")
            price = data.setdefault("price", {"data": [], "text": price_existing_text})
            if not price.get("data"):
                price["data"] = [{"AnnualFee": None, "CategoryMedianAnnualFee": fee, "FeeType": "Annual", "EndDate": ""}]
            else:
                price["data"][0]["CategoryMedianAnnualFee"] = fee
        except (TypeError, ValueError):
            pass

    # ── Is Index Fund (OF00C) ────────────────────────────────────────────────
    elif nk == "isindexfund" or dp_id == "OF00C":
        data["is_index_fund"] = _parse_optional_bool(dp_val)

    # ── Domicile Country (LS017) ──────────────────────────────────────────────
    elif nk in ("funddomicilecountry", "domicile") or dp_id == "LS017":
        if dp_val is not None:
            domicile = str(dp_val).strip()
            if domicile:
                data["domicile_country"] = domicile
                data["is_australian_domicile"] = _is_australia_domicile(domicile)
                _set_fund_info_value(data, "Domicile", domicile)

    # ── Is Australian Superannuation Fund (OS280) ────────────────────────────
    elif "isaustralian" in nk or dp_id == "OS280":
        data["is_australian_superannuation_fund"] = _parse_optional_bool(dp_val)

    # ── Investment Type (LS466) ────────────────────────────────────────────────
    elif nk == "investmenttype" or dp_id == "LS466":
        if dp_val is not None:
            investment_type = str(dp_val).strip()
            if investment_type:
                data["investment_type"] = investment_type
                _set_fund_info_value(data, "Investment Type", investment_type)

    # ── Disclosure Type (CNAXS) ────────────────────────────────────────────────
    elif nk == "disclosuretype" or dp_id == "CNAXS":
        if dp_val is not None:
            disclosure_str = str(dp_val).strip()
            if disclosure_str in ("Issuer Initiated Rating", "Tracks Morningstar Index"):
                data["disclosure_type"] = disclosure_str


# ---------------------------------------------------------------------------
# Main public functions
# ---------------------------------------------------------------------------

def normalize(
    lookup: dict,
    research_raw: dict,
    morningstar_id: str,
) -> dict[str, Any]:
    """Convert MCP analyst-research response into a formatter-compatible data dict.

    Parses narrative text content for pillar narratives and a best-effort
    text-based rating estimate.  Call ``supplement_with_datapoints()``
    immediately after to overwrite estimates with authoritative structured
    values from morningstar-data-tool.
    """
    results: list[dict] = research_raw.get("results") or []

    published_at  = results[0].get("published_at", "") if results else ""
    reference_url = results[0].get("url", "")          if results else ""
    content       = _concat_content(results)

    pillars                      = _extract_pillars(content)
    price_obj, price_score       = _extract_price(content)
    overall_rating, overall_text = _extract_overall(content)

    rating_symbol = _INT_TO_SYMBOL.get(overall_rating, "") if overall_rating is not None else ""

    fund_info = _build_fund_info(lookup, morningstar_id)
    if published_at:
        fund_info.append({"Attribute": "Research Published", "Value": published_at[:10]})
    if reference_url:
        fund_info.append({"Attribute": "Reference URL", "Value": reference_url})

    return {
        "share_class_id": morningstar_id,
        "morningstar_id": morningstar_id,
        "fund_info":      fund_info,

        "overall_rating": overall_rating,
        "overall_rating_raw": None,
        "rating_symbol":  rating_symbol,
        "rating_breakdown": {
            "weighted_score":  None,
            "formula_text":    "",
            "derivation_text": overall_text,
        },

        "historical_ratings":   [],
        "medalist_price_score": price_score,
        "price":                price_obj,

        "people_pillar":  pillars["people_pillar"],
        "process_pillar": pillars["process_pillar"],
        "parent_pillar":  pillars["parent_pillar"],

        "source":        "mcp",
        "published_at":  published_at,
        "reference_url": reference_url,
        "error":         None,

        # Fund attribute flags (populated by supplement_with_datapoints)
        "domicile_country":                 None,   # LS017 — country name/code
        "is_australian_domicile":           None,   # Derived from LS017
        "is_index_fund":                    None,   # OF00C — True/False/None
        "is_australian_superannuation_fund": None,  # OS280 — True/False/None
        "investment_type":                  None,   # LS466 — Investment vehicle type
        "disclosure_type":                  None,   # CNAXS — "Issuer Initiated Rating", "Tracks Morningstar Index", or None
    }


def supplement_with_datapoints(
    data: dict,
    datapoints_raw: dict,
    datapoint_ids: dict[str, str] | None = None,
) -> dict:
    """Enrich data with structured values from a morningstar-data-tool response.

    Accepts ``datapoints_raw`` — the pre-fetched raw response dict from the
    host agent's morningstar-data-tool call.  No network I/O is performed here.

    Structured values are AUTHORITATIVE — they overwrite any text-parsed
    estimates made by ``normalize()``.  Best-effort: exceptions are silently
    swallowed so the caller always receives a usable data dict.

    Parameters
    ----------
    data           Normalized dict returned by ``normalize()``.
    datapoints_raw Raw response dict from morningstar-data-tool
                   (e.g. ``{"result": {"<morningstar_id>": {"values": [...]}}}``).
    datapoint_ids  Optional mapping ``{"MedalistRating": "MMR01", …}``
                   as returned by the host agent's ID-discovery step.
                   Merged with ``KNOWN_DATAPOINT_IDS``.
    """
    morningstar_id = data.get("morningstar_id") or data.get("share_class_id", "")
    if not morningstar_id:
        return data

    ids_map: dict[str, str] = {**_DEFAULT_DATAPOINT_IDS}
    if datapoint_ids:
        ids_map.update(datapoint_ids)

    id_to_name: dict[str, str] = {v: k for k, v in ids_map.items()}

    try:
        fund_result = ((datapoints_raw.get("result") or {}).get(morningstar_id) or {})
        values      = fund_result.get("values") or []

        for v in values:
            dp_id   = v.get("datapointId", "")
            dp_val  = v.get("value")
            ts      = v.get("timeSeriesData") or []
            dp_name = id_to_name.get(dp_id) or v.get("datapointName", "")
            _apply_datapoint(data, dp_name, dp_id, dp_val, ts)

    except Exception:
        pass  # best-effort — never break the caller

    # Ensure rating_symbol stays consistent with overall_rating
    rating = data.get("overall_rating")
    if rating is not None and not data.get("rating_symbol"):
        try:
            data["rating_symbol"] = _INT_TO_SYMBOL.get(int(rating), "")
        except (TypeError, ValueError):
            pass

    return data


def build_data(
    lookup: dict,
    research_raw: dict,
    datapoints_raw: dict,
    history_raw: Any,
    morningstar_id: str,
    datapoint_ids: dict[str, str] | None = None,
) -> dict:
    """Build the complete normalized data dict from all pre-fetched MCP payloads.

    This is the high-level entry point for building the full normalized data dict.
    All payloads are supplied by the host agent — no network calls are made here.

    Parameters
    ----------
    lookup          Result dict from morningstar-id-lookup-tool
                    (keys: morningstar_id, investment_name, ticker, …).
    research_raw    Raw response from morningstar-analyst-research-tool
                    (shape: ``{"results": [{"content": "...", …}]}``).
    datapoints_raw  Raw response from morningstar-data-tool for current
                    datapoints (MMR01, MMR2E, MMR3E, MMR1E, MMRGS).
    history_raw     Raw response from morningstar-data-tool for historical
                    datapoints (MMR00, MMR1H, MMR2H, MMR3H), or None / {} to skip.
    morningstar_id  The fund's Morningstar ID string.
    datapoint_ids   Optional discovered datapoint ID mapping from the host agent.

    Returns
    -------
    Formatter-compatible data dict (same shape as documented in SKILL.md).
    On unrecoverable error returns ``{"error": "...", "morningstar_id": morningstar_id}``.
    """
    try:
        data = normalize(lookup, research_raw, morningstar_id)
        data = supplement_with_datapoints(data, datapoints_raw, datapoint_ids=datapoint_ids)

        if history_raw:
            try:
                history_rows = extract_historical_rows(history_raw)
                if history_rows:
                    merge_historical_rows(data, history_rows)
            except Exception as hist_exc:
                import sys as _sys
                print(
                    f"[data_normalizer WARNING] extract_historical_rows({morningstar_id}): "
                    f"{hist_exc}",
                    file=_sys.stderr,
                )

        return data

    except Exception as exc:
        return {"error": str(exc), "morningstar_id": morningstar_id}
