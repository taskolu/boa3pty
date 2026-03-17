from decimal import Decimal
from datetime import datetime
from typing import Optional
from src.core.models import WSEntry


# Default WallStreet column names (matches standard WallStreet paste format).
# Override individual keys via wallstreet_column_mapping in config.json
# to accommodate users with different column orders or renamed headers.
DEFAULT_WS_COLUMNS = {
    "deal_type":      "Deal Type",
    "value_date":     "Value Date",
    "counterparty":   "Customer",
    "pay_ccy":        "Pay Ccy",
    "pay_amount":     "Pay Amount",
    "rec_ccy":        "Rec Ccy",
    "rec_amount":     "Rec Amount",
    "rate":           "Rate",
    "trader":         "Trader",
    "wallstreet_ref": "Deal #",
    "external_ref":   "Ext Deal #",
}

# Aliases for each field — tried if exact match not found.
# Lower-cased for comparison.  Keep these SPECIFIC to avoid false matches.
_WS_ALIASES = {
    "external_ref": [
        "ext deal #", "ext deal#", "ext. deal #", "external ref",
        "external reference", "ext ref", "ext. ref", "external deal #",
        "ext deal no", "external deal no", "ext deal number",
        "external deal number",
    ],
    "value_date": [
        "value date", "val date", "vdate", "settlement date",
        "settle date", "value_date",
    ],
    "counterparty": [
        "customer", "counterparty", "client", "cp name",
        "counterparty name", "bank name",
    ],
    "pay_ccy": [
        "pay ccy", "pay currency", "payment currency", "sell ccy",
        "sell currency", "from ccy", "from currency",
    ],
    "pay_amount": [
        "pay amount", "payment amount", "sell amount", "from amount",
        "pay amt",
    ],
    "rec_ccy": [
        "rec ccy", "rec currency", "receive currency", "buy ccy",
        "buy currency", "to ccy", "to currency",
    ],
    "rec_amount": [
        "rec amount", "receive amount", "buy amount", "to amount",
        "rec amt",
    ],
    "rate": ["rate", "fx rate", "exchange rate", "exch rate", "all in rate"],
    "trader": ["trader", "dealer", "booked by", "entered by"],
    "deal_type": ["deal type", "type", "product", "instrument", "category"],
    "wallstreet_ref": [
        "deal #", "deal#", "deal no", "deal number", "ws ref",
        "internal ref",
    ],
}

_WS_DATE_FORMATS = [
    "%d %b %Y",   # 18 Mar 2026
    "%d-%b-%Y",   # 18-Mar-2026
    "%Y-%m-%d",   # 2026-03-18
    "%d/%m/%Y",   # 18/03/2026
    "%m/%d/%Y",   # 03/18/2026
    "%d %B %Y",   # 18 March 2026
]


def _resolve_col_idx(headers_lower: dict, field_key: str, override_name: str) -> Optional[int]:
    """
    Find the index for a field by checking:
      1. The exact override_name (from mapping, lowercased)
      2. All aliases for the field
    headers_lower: {lower_header_name: original_index}
    """
    # Exact match first
    if override_name.lower() in headers_lower:
        return headers_lower[override_name.lower()]
    # Alias match
    for alias in _WS_ALIASES.get(field_key, []):
        if alias in headers_lower:
            return headers_lower[alias]
    return None


def _parse_date(raw: str) -> object:
    for fmt in _WS_DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: {raw!r}")


def parse_wallstreet_paste(
    pasted_text: str,
    col_map_override: Optional[dict] = None,
) -> tuple[list[WSEntry], Optional[str]]:
    """Parse tab-separated WallStreet data from clipboard paste.

    Column order is determined by header names (with alias fallbacks), not
    position, so the paste works regardless of column arrangement.

    col_map_override: dict of {field_key: column_header_name} to override
                      any of the DEFAULT_WS_COLUMNS entries.

    Returns (list of WSEntry, detected counterparty name).
    Deduplicates rows by external_ref (Ext Deal #).
    """
    mapping = {**DEFAULT_WS_COLUMNS, **(col_map_override or {})}

    text = pasted_text.strip()
    if not text:
        return [], None

    lines = [l for l in text.splitlines() if l.strip()]

    # Find the header row: find a line containing a value_date-like column name
    header_line_idx = None
    vd_col_name = mapping["value_date"].lower()
    vd_aliases = [vd_col_name] + _WS_ALIASES.get("value_date", [])
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(alias in line_lower for alias in vd_aliases):
            header_line_idx = i
            break

    if header_line_idx is None:
        raise ValueError(
            "Could not find WallStreet header row "
            f"(looking for column '{mapping['value_date']}'). "
            f"First line seen: {lines[0][:80] if lines else '<empty>'!r}"
        )

    raw_headers = lines[header_line_idx].split("\t")
    # Build lookup: lower_header_name → index
    headers_lower = {h.strip().lower(): i for i, h in enumerate(raw_headers)}

    # Resolve column indices for all fields
    col_indices = {}
    for field_key, col_name in mapping.items():
        idx = _resolve_col_idx(headers_lower, field_key, col_name)
        col_indices[field_key] = idx

    def get(cells: list[str], field_key: str) -> str:
        idx = col_indices.get(field_key)
        if idx is None or idx >= len(cells):
            return ""
        return cells[idx].strip()

    # Pre-process: merge continuation lines.
    # WallStreet can split each row across multiple lines when the Customer
    # name contains a newline, AND again when columns overflow to a new line.
    # Strategy:
    #   - A new row starts when the first tab-cell is a pure integer (row #).
    #   - For continuation lines we need to decide whether to GLUE the first
    #     cell onto the previous row's last cell (broken mid-cell) or simply
    #     APPEND all cells as new columns (pure column overflow).
    #   - Heuristic: if the number of continuation cells == number of missing
    #     columns, it is a column overflow → append all. Otherwise it is a
    #     broken cell → glue first cell, append the rest.
    expected_cols = len(raw_headers)  # includes the empty leading row-# header
    raw_data_lines = [l for l in lines[header_line_idx + 1:] if l.strip()]
    merged_data_lines: list[str] = []
    for line in raw_data_lines:
        first_cell = line.split("\t")[0].strip()
        if first_cell.isdigit() or not merged_data_lines:
            merged_data_lines.append(line)
        else:
            prev_cells = merged_data_lines[-1].split("\t")
            cont_cells = line.split("\t")
            missing = expected_cols - len(prev_cells)
            if len(cont_cells) == missing:
                # Pure column overflow — append all cells without gluing
                merged_data_lines[-1] = "\t".join(prev_cells + cont_cells)
            else:
                # Broken mid-cell — glue first cell, then append the rest
                prev_cells[-1] = prev_cells[-1].strip() + " " + cont_cells[0].strip()
                merged_data_lines[-1] = "\t".join(prev_cells + cont_cells[1:])

    seen_external_refs: set[str] = set()
    entries: list[WSEntry] = []
    detected_counterparty: Optional[str] = None

    for line in merged_data_lines:
        cells = line.split("\t")
        if len(cells) < 3:
            continue

        ext_ref = get(cells, "external_ref")
        if not ext_ref:
            continue

        # Deduplicate: WallStreet pastes often contain sorted duplicates
        if ext_ref in seen_external_refs:
            continue
        seen_external_refs.add(ext_ref)

        deal_type = get(cells, "deal_type")
        if deal_type and deal_type.upper() not in ("FX", "SPOT", "FORWARD", ""):
            continue  # Skip non-FX rows (NDF, SWAP, etc.)

        counterparty = get(cells, "counterparty")
        if detected_counterparty is None and counterparty:
            detected_counterparty = counterparty

        raw_vd = get(cells, "value_date")
        value_date = _parse_date(raw_vd)

        def _decimal(s: str) -> Decimal:
            s = s.replace(",", "").replace(" ", "")
            return Decimal(s) if s else Decimal("0")

        entry = WSEntry(
            value_date=value_date,
            counterparty=counterparty,
            pay_ccy=get(cells, "pay_ccy"),
            pay_amount=_decimal(get(cells, "pay_amount")),
            rec_ccy=get(cells, "rec_ccy"),
            rec_amount=_decimal(get(cells, "rec_amount")),
            rate=_decimal(get(cells, "rate")),
            trader=get(cells, "trader"),
            wallstreet_ref=get(cells, "wallstreet_ref"),
            external_ref=ext_ref,
            deal_type=deal_type or "FX",
        )
        entries.append(entry)

    return entries, detected_counterparty


def get_detected_ws_headers(pasted_text: str) -> list[str]:
    """Return the raw headers found in the paste (for debugging)."""
    lines = [l for l in pasted_text.strip().splitlines() if l.strip()]
    vd_aliases = [DEFAULT_WS_COLUMNS["value_date"].lower()] + _WS_ALIASES.get("value_date", [])
    for line in lines:
        if any(alias in line.lower() for alias in vd_aliases):
            return [h.strip() for h in line.split("\t") if h.strip()]
    return []
