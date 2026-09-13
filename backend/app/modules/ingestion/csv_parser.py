import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass

# Maps a canonical field name to the set of header aliases (lowercased) that mean it.
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "company_name": ("company_name", "company", "name"),
    "domain": ("domain", "website", "url"),
    "industry": ("industry",),
    "employee_count_range": ("employee_count_range", "company_size", "employees"),
    "contact_full_name": ("contact_full_name", "contact_name"),
    "contact_role": ("contact_role", "role", "title", "job_title"),
    "contact_email": ("contact_email", "email"),
    "contact_phone": ("contact_phone", "phone", "mobile"),
    "notes": ("notes",),
}


@dataclass
class ParsedRow:
    row_number: int  # 1-indexed, excluding header
    fields: dict[str, str]
    error: str | None = None


@dataclass
class ParsedCsv:
    rows: list[ParsedRow]
    header_map: dict[str, str]  # canonical field -> original header found


def _build_header_map(fieldnames: Sequence[str]) -> dict[str, str]:
    lowered = {name.strip().lower(): name for name in fieldnames if name}
    header_map: dict[str, str] = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                header_map[canonical] = lowered[alias]
                break
    return header_map


def parse_csv(raw_text: str) -> ParsedCsv:
    reader = csv.DictReader(io.StringIO(raw_text))
    header_map = _build_header_map(reader.fieldnames or [])

    rows: list[ParsedRow] = []
    for i, raw_row in enumerate(reader, start=1):
        fields = {
            canonical: (raw_row.get(original) or "").strip()
            for canonical, original in header_map.items()
        }
        error = None
        if not fields.get("company_name") and not fields.get("domain"):
            error = "row has neither a company name nor a domain"
        rows.append(ParsedRow(row_number=i, fields=fields, error=error))

    return ParsedCsv(rows=rows, header_map=header_map)
